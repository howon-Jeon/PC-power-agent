from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_FILE = "config.json"
APP_VERSION = 2
APP_DISPLAY_VERSION = "1.0.3"
CRYPTPROTECT_LOCAL_MACHINE = 0x4


class ConfigError(RuntimeError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_config_path() -> Path:
    return app_dir() / DEFAULT_CONFIG_FILE


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _bytes_from_blob(blob: DATA_BLOB) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def _dpapi_protect(data: bytes) -> str:
    if os.name != "nt":
        return base64.b64encode(data).decode("ascii")

    crypt32 = ctypes.windll.crypt32
    in_blob = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_LOCAL_MACHINE,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ConfigError("DPAPI encryption failed")
    return base64.b64encode(_bytes_from_blob(out_blob)).decode("ascii")


def _dpapi_unprotect(value: str) -> bytes:
    encrypted = base64.b64decode(value)
    if os.name != "nt":
        return encrypted

    crypt32 = ctypes.windll.crypt32
    in_blob = _blob_from_bytes(encrypted)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ConfigError("DPAPI decryption failed")
    return _bytes_from_blob(out_blob)


def validate_port(port: int) -> int:
    if not 1 <= port <= 65535:
        raise ConfigError("port must be in range 1..65535")
    return port


def validate_key(key: bytes) -> bytes:
    if len(key) != 32:
        raise ConfigError("AES-GCM key must be 32 bytes")
    return key


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["port"] = validate_port(int(raw["port"]))
    raw["aes_key"] = validate_key(_dpapi_unprotect(raw["aes_key_protected"]))
    return raw


def save_config(
    *,
    port: int,
    aes_key: bytes,
    path: Path | None = None,
    shutdown_enabled: bool = False,
    response_port: int | None = None,
    startup_notify_host: str | None = None,
    startup_notify_port: int | None = None,
    startup_notify_retries: int = 3,
    status_interval_seconds: int = 20,
    command_codes: dict[str, str] | None = None,
    response_codes: dict[str, str] | None = None,
) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    validate_port(port)
    validate_key(aes_key)
    if response_port is not None and not 1 <= int(response_port) <= 65535:
        raise ConfigError("response_port must be in range 1..65535")
    if startup_notify_port is not None and not 1 <= int(startup_notify_port) <= 65535:
        raise ConfigError("startup_notify_port must be in range 1..65535")

    data: dict[str, Any] = {
        "version": APP_VERSION,
        "port": port,
        "response_port": response_port,
        "packet_format": "nonce_ciphertext_tag",
        "shutdown_enabled": shutdown_enabled,
        "startup_notify_host": startup_notify_host,
        "startup_notify_port": startup_notify_port,
        "startup_notify_retries": startup_notify_retries,
        "status_interval_seconds": status_interval_seconds,
        "aes_key_protected": _dpapi_protect(aes_key),
        "command_codes": command_codes
        or {
            "shutdown": "1001",
            "status": "1002",
        },
        "response_codes": response_codes
        or {
            "online": "2001",
            "shutdown_accepted": "2002",
            "unknown_command": "4001",
            "command_failed": "5001",
        },
    }
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return config_path
