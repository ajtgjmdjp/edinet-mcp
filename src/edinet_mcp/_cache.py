"""Simple disk-based cache for downloaded EDINET documents."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
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

    def get_json(
        self, namespace: str, params: dict[str, Any], *, max_age: float | None = None
    ) -> Any | None:
        """Retrieve a cached JSON response, or None if miss/expired.

        Args:
            namespace: Cache namespace.
            params: Parameters that uniquely identify the entry.
            max_age: Maximum age in seconds. ``None`` means no expiry.
        """
        path = self._dir / namespace / f"{self._key(namespace, params)}.json"
        try:
            if max_age is not None and (time.time() - path.stat().st_mtime) > max_age:
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            # A corrupt entry (partial write, disk issue) must act as a
            # cache miss and be removed so the next fetch repopulates it —
            # otherwise every call fails until manual cleanup.
            path.unlink(missing_ok=True)
            return None

    def put_json(self, namespace: str, params: dict[str, Any], data: Any) -> Path:
        """Store a JSON response in the cache. Returns the file path."""
        ns_dir = self._dir / namespace
        ns_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = ns_dir / f"{self._key(namespace, params)}.json"
        _write_restricted(path, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
        return path

    def get_file(
        self,
        namespace: str,
        params: dict[str, Any],
        suffix: str = "",
        *,
        max_age: float | None = None,
    ) -> Path | None:
        """Retrieve a cached binary file path, or None if miss/expired.

        Args:
            namespace: Cache namespace.
            params: Parameters that uniquely identify the entry.
            suffix: File extension (e.g. ``".zip"``).
            max_age: Maximum age in seconds. ``None`` means no expiry.
        """
        path = self._dir / namespace / f"{self._key(namespace, params)}{suffix}"
        if not path.exists():
            return None
        if max_age is not None and (time.time() - path.stat().st_mtime) > max_age:
            return None
        return path

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
    """Write data atomically with owner-only permissions (0o600).

    Writes to a same-directory temporary file (O_EXCL, so a planted
    symlink is never followed), fsyncs, then atomically replaces the
    destination. Concurrent readers therefore never observe partial
    JSON/ZIP data, and a crashed writer leaves the old entry intact.
    """
    tmp_path = path.parent / f".{path.name}.tmp-{os.getpid()}"
    fd = os.open(
        str(tmp_path),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        tmp_path.unlink(missing_ok=True)
        raise
    os.close(fd)
    os.replace(tmp_path, path)
