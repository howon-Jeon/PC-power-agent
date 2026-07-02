from __future__ import annotations

import argparse
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
    packet = encrypt_packet(
        config["aes_key"],
        build_framed_response(status),
        config.get("packet_format", "nonce_ciphertext_tag"),
    )
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(packet, (str(notify_host), notify_port))
        LOGGER.info("sent status=%s reason=%s to %s:%s", status, reason, notify_host, notify_port)
    except OSError:
        LOGGER.exception("failed to send status=%s reason=%s to %s:%s", status, reason, notify_host, notify_port)


def send_online_status(sock: socket.socket, config: dict[str, Any], reason: str) -> None:
    send_status(sock, config, "online", reason)


def handle_packet(sock: socket.socket, data: bytes, source: tuple[str, int], config: dict[str, Any]) -> bool:
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
        status_interval = max(0, int(config.get("status_interval_seconds") or 0))
        next_status_at = time.monotonic() + status_interval if status_interval else 0
        shutting_down = False

        while not STOP_EVENT.is_set():
            if status_interval and time.monotonic() >= next_status_at:
                if shutting_down:
                    send_status(sock, config, "shutdown_accepted", "periodic_shutdown")
                else:
                    send_online_status(sock, config, "periodic")
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
            if handle_packet(sock, data, source, config):
                shutting_down = True

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
