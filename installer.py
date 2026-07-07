from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from config_store import APP_VERSION, ConfigError, default_config_path, save_config, validate_port


FIXED_AES_KEY = "tCF2fFU8827lb23wEXzbZhB3IMHT09zM"
FIXED_NOTIFY_HOST = "255.255.255.255"


def parse_key(value: str) -> bytes:
    cleaned = value.strip()
    try:
        if len(cleaned) == 64:
            return bytes.fromhex(cleaned)
        if len(cleaned.encode("utf-8")) == 32:
            return cleaned.encode("utf-8")
        return base64.b64decode(cleaned, validate=True)
    except ValueError as exc:
        raise ConfigError("key must be 32-byte text, 64-byte hex, or base64") from exc


def parse_pc_port(value: str) -> int:
    return validate_port(int(value.strip()))


def fetch_install_config(server_url: str, install_code: str) -> tuple[int, bytes, str | None, int | None]:
    body = json.dumps({"install_code": install_code}).encode("utf-8")
    request = urllib.request.Request(
        server_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ConfigError(f"install server request failed: {exc}") from exc

    try:
        port = validate_port(int(payload["port"]))
        aes_key = parse_key(str(payload["aes_key"]))
        notify_host = payload.get("startup_notify_host")
        notify_port = payload.get("startup_notify_port")
        notify_port = validate_port(int(notify_port)) if notify_port else None
    except KeyError as exc:
        raise ConfigError(f"install server response missing field: {exc}") from exc
    return port, aes_key, notify_host, notify_port


def interactive_args() -> tuple[int, bytes, str | None, int | None]:
    print(f"프로그램 버전: {APP_VERSION}")
    port = parse_pc_port(input("앱 기능 설정과 동일하게 UDP 포트 번호를 입력해주세요 : "))
    return port, parse_key(FIXED_AES_KEY), FIXED_NOTIFY_HOST, port


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Configure PC power agent")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--manual", action="store_true", help="configure with direct port/key input")
    parser.add_argument("--port", type=int)
    parser.add_argument("--key-hex")
    parser.add_argument("--key-base64")
    parser.add_argument("--notify-host", help="controller IP or broadcast address for startup online notification")
    parser.add_argument("--notify-port", type=int, help="controller UDP port for startup online notification")
    parser.add_argument("--status-interval", type=int, default=5, help="seconds between periodic #PC_STATUS:1& notifications")
    parser.add_argument("--server-url", help="install-code exchange endpoint")
    parser.add_argument("--install-code", help="6-digit install code")
    parser.add_argument("--enable-shutdown", action="store_true", help="allow real Windows shutdown")
    args = parser.parse_args()

    try:
        if args.server_url and args.install_code:
            port, aes_key, notify_host, notify_port = fetch_install_config(args.server_url, args.install_code)
            notify_host = args.notify_host or notify_host
            notify_port = validate_port(args.notify_port) if args.notify_port else notify_port
        elif args.manual and args.port:
            port = validate_port(args.port)
            aes_key = parse_key(args.key_hex or args.key_base64 or FIXED_AES_KEY)
            notify_host = args.notify_host or FIXED_NOTIFY_HOST
            notify_port = validate_port(args.notify_port) if args.notify_port else port
        elif args.manual:
            port, aes_key, notify_host, notify_port = interactive_args()
        else:
            parser.error("use --manual or provide --server-url and --install-code")

        path = save_config(
            port=port,
            aes_key=aes_key,
            path=args.config,
            shutdown_enabled=args.enable_shutdown,
            startup_notify_host=notify_host,
            startup_notify_port=notify_port,
            status_interval_seconds=args.status_interval,
        )
    except (ConfigError, ValueError) as exc:
        print(f"install error: {exc}", file=sys.stderr)
        return 2

    print(f"config saved: {path}")
    print(f"udp port: {port}")
    print("aes key : 인증 완료")
    print(f"shutdown enabled: {args.enable_shutdown}")
    print(f"startup notify: {notify_host or 'disabled'}:{notify_port or ''}")
    print(f"status interval seconds: {args.status_interval}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
