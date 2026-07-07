from __future__ import annotations

import argparse
import ctypes
import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from config_store import ConfigError, default_config_path, load_config
from crypto_codec import PacketCryptoError, decrypt_packet, encrypt_packet
from protocol import build_framed_response, build_response, parse_command


LOGGER = logging.getLogger("pc_agent")
STOP_EVENT = threading.Event()
WINDOWS_SHUTDOWN_EVENT = threading.Event()
SM_SHUTTINGDOWN = 0x2000
SHUTDOWN_STATUS_INTERVAL_SECONDS = 3
SHUTDOWN_EVENT_LOOKBACK_MS = 15000
SHUTDOWN_EVENT_ARM_DELAY_SECONDS = 20
SHUTDOWN_BURST_COUNT = 3
SHUTDOWN_BURST_INTERVAL_SECONDS = 0.15
SHUTDOWN_STUCK_RECOVERY_SECONDS = 120


def setup_logging(foreground: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)] if foreground else []
    if not handlers:
        log_path = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent / "pc_agent.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def execute_shutdown(enabled: bool) -> tuple[bool, str]:
    if not enabled:
        LOGGER.warning("shutdown command received, but shutdown is disabled")
        return True, "shutdown dry-run accepted"

    try:
        subprocess.Popen(["shutdown", "/s", "/t", "5", "/c", "Remote power control request"])
        return True, "shutdown scheduled"
    except OSError as exc:
        LOGGER.exception("failed to schedule shutdown")
        return False, str(exc)


def is_windows_shutting_down() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.user32.GetSystemMetrics(SM_SHUTTINGDOWN))
    except (AttributeError, OSError):
        return False


def has_recent_windows_shutdown_event() -> bool:
    if sys.platform != "win32":
        return False

    query = f"*[System[(EventID=1074) and TimeCreated[timediff(@SystemTime) <= {SHUTDOWN_EVENT_LOOKBACK_MS}]]]"
    try:
        result = subprocess.run(
            ["wevtutil", "qe", "System", "/c:1", "/rd:true", "/f:text", f"/q:{query}"],
            capture_output=True,
            text=True,
            timeout=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0 and bool(result.stdout.strip())


def detect_windows_shutdown(use_event_log: bool) -> bool:
    if WINDOWS_SHUTDOWN_EVENT.is_set() or is_windows_shutting_down():
        return True
    return use_event_log and has_recent_windows_shutdown_event()


def send_response(sock: socket.socket, source: tuple[str, int], config: dict[str, Any], request: dict[str, Any], code: str, status: str, message: str = "") -> None:
    response_port = config.get("response_port") or source[1]
    if request.get("protocol") == "framed":
        response_plain = build_framed_response(status)
    else:
        response_plain = build_response(code, status, request, message)
    response_packet = encrypt_packet(config["aes_key"], response_plain, config.get("packet_format", "nonce_ciphertext_tag"))
    sock.sendto(response_packet, (source[0], int(response_port)))
    LOGGER.info("sent response code=%s status=%s to %s:%s", code, status, source[0], response_port)


def send_startup_notification(sock: socket.socket, config: dict[str, Any]) -> None:
    notify_host = config.get("startup_notify_host")
    if not notify_host:
        LOGGER.info("startup notification disabled")
        return

    notify_port = int(config.get("startup_notify_port") or config["port"])
    retries = max(1, int(config.get("startup_notify_retries") or 1))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    for attempt in range(1, retries + 1):
        try:
            packet = encrypt_packet(
                config["aes_key"],
                build_framed_response("online"),
                config.get("packet_format", "nonce_ciphertext_tag"),
            )
            sock.sendto(packet, (str(notify_host), notify_port))
            LOGGER.info("sent startup notification attempt=%s to %s:%s", attempt, notify_host, notify_port)
        except OSError:
            LOGGER.exception("failed to send startup notification attempt=%s to %s:%s", attempt, notify_host, notify_port)
        if attempt < retries:
            time.sleep(1)


def send_status(sock: socket.socket, config: dict[str, Any], status: str, reason: str) -> None:
    notify_host = config.get("startup_notify_host")
    if not notify_host:
        return

    notify_port = int(config.get("startup_notify_port") or config["port"])
    plaintext = build_framed_response(status)
    packet = encrypt_packet(
        config["aes_key"],
        plaintext,
        config.get("packet_format", "nonce_ciphertext_tag"),
    )
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(packet, (str(notify_host), notify_port))
        LOGGER.info("sent status=%s reason=%s payload=%r to %s:%s", status, reason, plaintext, notify_host, notify_port)
    except OSError:
        LOGGER.exception("failed to send status=%s reason=%s payload=%r to %s:%s", status, reason, plaintext, notify_host, notify_port)


def send_status_burst(sock: socket.socket, config: dict[str, Any], status: str, reason: str) -> None:
    for attempt in range(SHUTDOWN_BURST_COUNT):
        send_status(sock, config, status, reason)
        if attempt < SHUTDOWN_BURST_COUNT - 1:
            time.sleep(SHUTDOWN_BURST_INTERVAL_SECONDS)


def enter_shutdown_status_mode(sock: socket.socket, config: dict[str, Any], reason: str, now: float) -> float:
    send_status_burst(sock, config, "shutdown_accepted", reason)
    return now + SHUTDOWN_STATUS_INTERVAL_SECONDS


def request_shutdown_status_mode() -> None:
    WINDOWS_SHUTDOWN_EVENT.set()


def notify_windows_shutdown(config_path: Path, reason: str = "windows_service_shutdown") -> None:
    config = load_config(config_path)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        send_status_burst(sock, config, "shutdown_accepted", reason)


def handle_packet(sock: socket.socket, data: bytes, source: tuple[str, int], config: dict[str, Any], current_status: str = "online") -> bool:
    try:
        plaintext = decrypt_packet(config["aes_key"], data)
        request = parse_command(plaintext)
    except (PacketCryptoError, ValueError, UnicodeDecodeError) as exc:
        LOGGER.info("ignored invalid packet from %s:%s: %s", source[0], source[1], exc)
        return False

    code = str(request["code"])
    command_codes = config["command_codes"]
    response_codes = config["response_codes"]
    LOGGER.info("received command code=%s from %s:%s", code, source[0], source[1])

    if code == "ACK":
        LOGGER.info("received controller ACK from %s:%s", source[0], source[1])
        return False

    if code == command_codes["status"]:
        if current_status == "shutdown_accepted":
            send_response(sock, source, config, request, response_codes["shutdown_accepted"], "shutdown_accepted")
        else:
            send_response(sock, source, config, request, response_codes["online"], "online")
        return False

    if code == command_codes["shutdown"]:
        ok, message = execute_shutdown(bool(config.get("shutdown_enabled", False)))
        if ok:
            send_response(sock, source, config, request, response_codes["shutdown_accepted"], "shutdown_accepted", message)
            LOGGER.info("shutdown accepted; periodic status will report offline")
            return True
        else:
            send_response(sock, source, config, request, response_codes["command_failed"], "failed", message)
        return False

    send_response(sock, source, config, request, response_codes["unknown_command"], "unknown_command", f"unknown command: {code}")
    return False


def run_agent(config_path: Path, foreground: bool = False) -> None:
    setup_logging(foreground)
    config = load_config(config_path)
    port = int(config["port"])

    LOGGER.info("starting UDP listener on 0.0.0.0:%s", port)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        sock.settimeout(1.0)
        send_startup_notification(sock, config)
        normal_status_interval = max(0, int(config.get("status_interval_seconds") or 0))
        status_interval = normal_status_interval
        next_status_at = time.monotonic() + status_interval if status_interval else 0
        current_status = "online"
        shutdown_immediate_sent = False
        shutdown_accepted_at: float | None = None
        event_log_detection_at = time.monotonic() + SHUTDOWN_EVENT_ARM_DELAY_SECONDS

        def enter_shutdown(reason: str, now: float) -> None:
            nonlocal current_status, status_interval, next_status_at, shutdown_immediate_sent, shutdown_accepted_at
            current_status = "shutdown_accepted"
            status_interval = SHUTDOWN_STATUS_INTERVAL_SECONDS
            shutdown_accepted_at = now
            if not shutdown_immediate_sent:
                next_status_at = enter_shutdown_status_mode(sock, config, reason, now)
                shutdown_immediate_sent = True

        def recover_if_shutdown_stuck(now: float) -> None:
            nonlocal current_status, status_interval, next_status_at, shutdown_immediate_sent, shutdown_accepted_at
            if (
                current_status == "shutdown_accepted"
                and shutdown_accepted_at is not None
                and now - shutdown_accepted_at >= SHUTDOWN_STUCK_RECOVERY_SECONDS
            ):
                LOGGER.warning("shutdown appears to have been aborted; resetting shutdown tracking")
                current_status = "online"
                status_interval = normal_status_interval
                next_status_at = now + normal_status_interval if normal_status_interval else 0
                shutdown_immediate_sent = False
                shutdown_accepted_at = None
                WINDOWS_SHUTDOWN_EVENT.clear()

        while not STOP_EVENT.is_set():
            now = time.monotonic()
            recover_if_shutdown_stuck(now)
            if current_status != "shutdown_accepted" and detect_windows_shutdown(now >= event_log_detection_at):
                enter_shutdown("windows_shutdown_detected", now)

            if status_interval and now >= next_status_at:
                reason = "periodic_shutdown" if current_status == "shutdown_accepted" else "periodic"
                send_status(sock, config, current_status, reason)
                next_status_at = time.monotonic() + status_interval

            try:
                data, source = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except ConnectionResetError as exc:
                LOGGER.info("ignored UDP connection reset: %s", exc)
                continue
            except OSError:
                if STOP_EVENT.is_set():
                    break
                raise

            now = time.monotonic()
            if current_status != "shutdown_accepted" and detect_windows_shutdown(now >= event_log_detection_at):
                enter_shutdown("windows_shutdown_detected", now)

            if handle_packet(sock, data, source, config, current_status):
                enter_shutdown("shutdown_command_accepted", time.monotonic())

    LOGGER.info("UDP listener stopped")


def stop_agent() -> None:
    STOP_EVENT.set()


def main() -> int:
    parser = argparse.ArgumentParser(description="PC UDP power-control agent")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--foreground", action="store_true", help="log to console")
    args = parser.parse_args()

    try:
        run_agent(args.config, args.foreground)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
