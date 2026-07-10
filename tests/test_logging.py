from __future__ import annotations

import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest import mock

import pc_agent


class LoggingConfigurationTests(unittest.TestCase):
    def tearDown(self) -> None:
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

    def test_service_logging_uses_bounded_rotating_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                executable = str(Path(temp_dir) / "pc_agent_service.exe")
                with mock.patch.object(pc_agent.sys, "frozen", True, create=True):
                    with mock.patch.object(pc_agent.sys, "executable", executable):
                        pc_agent.setup_logging(foreground=False)

                handlers = [
                    handler
                    for handler in logging.getLogger().handlers
                    if isinstance(handler, RotatingFileHandler)
                ]
                self.assertEqual(len(handlers), 1)
                self.assertEqual(handlers[0].maxBytes, pc_agent.LOG_MAX_BYTES)
                self.assertEqual(handlers[0].backupCount, pc_agent.LOG_BACKUP_COUNT)
            finally:
                self.tearDown()


if __name__ == "__main__":
    unittest.main()
