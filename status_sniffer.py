from __future__ import annotations

import argparse
import time
from pathlib import Path

from config_store import default_config_path, load_config
from crypto_codec import PacketCryptoError, decrypt_packet


def main() -> int:
    parser = argparse.ArgumentParser(description="Passively decrypt and print PC agent status broadcasts")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--port", type=int, help="override listen port (defaults to startup_notify_port or port)")
    args = parser.parse_args()

    config = load_config(args.config)
    port = args.port or int(config.get("startup_notify_port") or config["port"])

    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        print(f"listening on 0.0.0.0:{port} (Ctrl+C to stop)")
        while True:
            try:
                data, source = sock.recvfrom(4096)
            except KeyboardInterrupt:
                return 0
            ts = time.strftime("%H:%M:%S")
            try:
                plaintext = decrypt_packet(config["aes_key"], data)
                print(f"[{ts}] from {source[0]}:{source[1]} -> {plaintext!r}")
            except (PacketCryptoError, ValueError) as exc:
                print(f"[{ts}] from {source[0]}:{source[1]} -> decrypt failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
