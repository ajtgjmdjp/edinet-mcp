"""Simple disk-based cache for downloaded EDINET documents."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class DiskCache:
    """File-system cache keyed by request parameters.

    Stores API responses and downloaded files on disk to avoid
    redundant network calls. Each entry is a JSON file (for metadata)
    or a raw file (for ZIP/XBRL downloads).

    Args:
        cache_dir: Root directory for the cache.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _key(self, namespace: str, params: dict[str, Any]) -> str:
        raw = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(f"{namespace}:{raw}".encode()).hexdigest()[:16]

    def get_json(self, namespace: str, params: dict[str, Any]) -> Any | None:
        """Retrieve a cached JSON response, or None if miss."""
        path = self._dir / namespace / f"{self._key(namespace, params)}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def put_json(self, namespace: str, params: dict[str, Any], data: Any) -> Path:
        """Store a JSON response in the cache. Returns the file path."""
        ns_dir = self._dir / namespace
        ns_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = ns_dir / f"{self._key(namespace, params)}.json"
        _write_restricted(path, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
        return path

    def get_file(self, namespace: str, params: dict[str, Any], suffix: str = "") -> Path | None:
        """Retrieve a cached binary file path, or None if miss."""
        path = self._dir / namespace / f"{self._key(namespace, params)}{suffix}"
        return path if path.exists() else None

    def put_file(
        self, namespace: str, params: dict[str, Any], data: bytes, suffix: str = ""
    ) -> Path:
        """Store binary data in the cache. Returns the file path."""
        ns_dir = self._dir / namespace
        ns_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = ns_dir / f"{self._key(namespace, params)}{suffix}"
        _write_restricted(path, data)
        return path

    def clear(self) -> None:
        """Remove all cached entries."""
        import shutil

        if self._dir.exists():
            shutil.rmtree(self._dir)
            self._dir.mkdir(parents=True, exist_ok=True, mode=0o700)


def _write_restricted(path: Path, data: bytes) -> None:
    """Write data to a file with owner-only permissions (0o600)."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
