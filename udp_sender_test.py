from __future__ import annotations

import argparse
import json
import socket
import uuid

from crypto_codec import decrypt_packet, encrypt_packet
from installer import parse_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypted UDP sender for PC power-agent tests")
    parser.add_argument("--host", default="255.255.255.255")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--key-hex")
    parser.add_argument("--key-base64")
    parser.add_argument("--command", default="1002")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    key = parse_key(args.key_hex or args.key_base64 or "")
    request = {
        "code": str(args.command),
        "request_id": str(uuid.uuid4()),
    }
    packet = encrypt_packet(key, json.dumps(request, separators=(",", ":")).encode("utf-8"))

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(args.timeout)
        sock.sendto(packet, (args.host, args.port))
        print(f"sent command {args.command} to {args.host}:{args.port}")
        try:
            response, source = sock.recvfrom(4096)
        except socket.timeout:
            print("no response")
            return 1

    plaintext = decrypt_packet(key, response)
    print(f"response from {source[0]}:{source[1]}")
    print(plaintext.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
