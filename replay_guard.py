from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path


class ReplayGuardError(RuntimeError):
    pass


class PersistentReplayGuard:
    """Persist packet fingerprints so an accepted command cannot run twice."""

    def __init__(self, path: Path, max_entries: int = 10000):
        self.path = path
        self.max_entries = max(1, max_entries)
        self._lock = threading.Lock()
        self._fingerprints: list[str] = []
        self._seen: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return

        try:
            lines = self.path.read_text(encoding="ascii").splitlines()
        except OSError as exc:
            raise ReplayGuardError(f"failed to read replay cache: {self.path}") from exc

        for value in lines[-self.max_entries :]:
            fingerprint = value.strip().lower()
            if len(fingerprint) == 64 and all(char in "0123456789abcdef" for char in fingerprint):
                if fingerprint not in self._seen:
                    self._seen.add(fingerprint)
                    self._fingerprints.append(fingerprint)

    def claim(self, packet: bytes) -> bool:
        """Return True once for a packet and False for every exact replay."""
        fingerprint = hashlib.sha256(packet).hexdigest()
        with self._lock:
            if fingerprint in self._seen:
                return False

            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self.path.open("a", encoding="ascii", newline="\n") as cache_file:
                    cache_file.write(f"{fingerprint}\n")
                    cache_file.flush()
                    os.fsync(cache_file.fileno())
            except OSError as exc:
                raise ReplayGuardError(f"failed to update replay cache: {self.path}") from exc

            self._seen.add(fingerprint)
            self._fingerprints.append(fingerprint)
            if len(self._fingerprints) > self.max_entries:
                self._compact()
            return True

    def _compact(self) -> None:
        retained = self._fingerprints[-self.max_entries :]
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        try:
            temporary_path.write_text("".join(f"{value}\n" for value in retained), encoding="ascii")
            os.replace(temporary_path, self.path)
        except OSError as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise ReplayGuardError(f"failed to compact replay cache: {self.path}") from exc

        self._fingerprints = retained
        self._seen = set(retained)
