from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crypto_codec import encrypt_packet
from pc_agent import handle_packet
from replay_guard import PersistentReplayGuard


class FakeSocket:
    def __init__(self) -> None:
        self.sent_packets: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, packet: bytes, target: tuple[str, int]) -> None:
        self.sent_packets.append((packet, target))


class PersistentReplayGuardTests(unittest.TestCase):
    def test_rejects_same_packet_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "replay_cache.log"
            packet = b"encrypted-shutdown-packet"

            first_process = PersistentReplayGuard(cache_path)
            self.assertTrue(first_process.claim(packet))
            self.assertFalse(first_process.claim(packet))

            restarted_process = PersistentReplayGuard(cache_path)
            self.assertFalse(restarted_process.claim(packet))

    def test_accepts_different_packets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = PersistentReplayGuard(Path(temp_dir) / "replay_cache.log")

            self.assertTrue(guard.claim(b"packet-one"))
            self.assertTrue(guard.claim(b"packet-two"))

    @mock.patch("pc_agent.execute_shutdown", return_value=(True, "shutdown scheduled"))
    def test_duplicate_shutdown_packet_is_not_executed_twice(self, execute_shutdown: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            key = b"tCF2fFU8827lb23wEXzbZhB3IMHT09zM"
            packet = encrypt_packet(key, b"#PC_POWER_OFF&")
            config = {
                "aes_key": key,
                "packet_format": "nonce_ciphertext_tag",
                "shutdown_enabled": True,
                "command_codes": {"shutdown": "1001", "status": "1002"},
                "response_codes": {
                    "online": "2001",
                    "shutdown_accepted": "2002",
                    "unknown_command": "4001",
                    "command_failed": "5001",
                },
            }
            replay_guard = PersistentReplayGuard(Path(temp_dir) / "replay_cache.log")
            sock = FakeSocket()

            self.assertTrue(handle_packet(sock, packet, ("192.168.10.121", 8008), config, replay_guard=replay_guard))
            self.assertFalse(handle_packet(sock, packet, ("192.168.10.121", 8008), config, replay_guard=replay_guard))

            execute_shutdown.assert_called_once_with(True)
            self.assertEqual(len(sock.sent_packets), 2)


if __name__ == "__main__":
    unittest.main()
