from __future__ import annotations

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


NONCE_SIZE = 12
TAG_SIZE = 16
PACKET_NONCE_TAG_CIPHERTEXT = "nonce_tag_ciphertext"
PACKET_NONCE_CIPHERTEXT_TAG = "nonce_ciphertext_tag"


class PacketCryptoError(RuntimeError):
    pass


def encrypt_packet(key: bytes, plaintext: bytes, packet_format: str = PACKET_NONCE_CIPHERTEXT_TAG) -> bytes:
    nonce = get_random_bytes(NONCE_SIZE)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_SIZE)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    if packet_format == PACKET_NONCE_TAG_CIPHERTEXT:
        return nonce + tag + ciphertext
    if packet_format == PACKET_NONCE_CIPHERTEXT_TAG:
        return nonce + ciphertext + tag
    raise PacketCryptoError(f"unsupported packet format: {packet_format}")


def decrypt_packet(key: bytes, packet: bytes) -> bytes:
    if len(packet) <= NONCE_SIZE + TAG_SIZE:
        raise PacketCryptoError("packet is too short")

    nonce = packet[:NONCE_SIZE]
    errors: list[ValueError] = []
    candidates = (
        (packet[NONCE_SIZE : NONCE_SIZE + TAG_SIZE], packet[NONCE_SIZE + TAG_SIZE :]),
        (packet[-TAG_SIZE:], packet[NONCE_SIZE:-TAG_SIZE]),
    )
    for tag, ciphertext in candidates:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_SIZE)
        try:
            return cipher.decrypt_and_verify(ciphertext, tag)
        except ValueError as exc:
            errors.append(exc)
    raise PacketCryptoError("packet authentication failed") from errors[-1]
