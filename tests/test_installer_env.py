from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import installer
from config_store import ConfigError


class InstallerEnvTests(unittest.TestCase):
    def test_loads_aes_key_from_environment_variable(self) -> None:
        key = "0123456789abcdef0123456789abcdef"

        with mock.patch.dict("os.environ", {installer.AES_KEY_ENV_NAME: key}, clear=False):
            self.assertEqual(installer.load_aes_key_from_env(), key.encode("utf-8"))

    def test_loads_aes_key_from_env_file(self) -> None:
        key = "abcdef0123456789abcdef0123456789"

        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(f"{installer.AES_KEY_ENV_NAME}={key}\n", encoding="utf-8")

            with mock.patch.dict("os.environ", {}, clear=True):
                with mock.patch("installer.runtime_dir", return_value=Path(temp_dir)):
                    self.assertEqual(installer.load_aes_key_from_env(), key.encode("utf-8"))

    def test_missing_aes_key_fails_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict("os.environ", {}, clear=True):
                with mock.patch("installer.runtime_dir", return_value=Path(temp_dir)):
                    with self.assertRaises(ConfigError):
                        installer.load_aes_key_from_env()


if __name__ == "__main__":
    unittest.main()
