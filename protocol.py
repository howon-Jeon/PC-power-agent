from __future__ import annotations

import json
import time
import uuid
from typing import Any


def parse_command(plaintext: bytes) -> dict[str, Any]:
    text = plaintext.decode("utf-8").strip()
    if not text:
        raise ValueError("empty command")

    if text.startswith("#") and text.endswith("&"):
        body = text[1:-1].strip().upper()
        if body == "PC_POWER_OK" or body.startswith("PC_STATUS:"):
            return {"code": "ACK", "raw": text, "protocol": "framed"}
        if body in {"PC_STATUS", "STATUS"}:
            return {"code": "1002", "raw": text, "protocol": "framed"}
        if body in {"PC_POWER_OFF", "PC_SHUTDOWN", "SHUTDOWN", "OFF"}:
            return {"code": "1001", "raw": text, "protocol": "framed"}
        return {"code": body, "raw": text, "protocol": "framed"}

    if text.startswith("{"):
        payload = json.loads(text)
        if "code" not in payload:
            raise ValueError("JSON command requires 'code'")
        payload["code"] = str(payload["code"])
        return payload

    return {"code": text}


def build_framed_response(status: str) -> bytes:
    if status == "online":
        return b"#PC_STATUS:1&"
    if status == "shutdown_accepted":
        return b"#PC_STATUS:0&"
    if status == "failed":
        return b"#PC_STATUS:ERROR&"
    return b"#PC_STATUS:UNKNOWN&"


def build_response(code: str, status: str, request: dict[str, Any] | None = None, message: str = "") -> bytes:
    request = request or {}
    payload = {
        "code": code,
        "status": status,
        "message": message,
        "request_id": request.get("request_id"),
        "agent_time": int(time.time()),
        "response_id": str(uuid.uuid4()),
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
