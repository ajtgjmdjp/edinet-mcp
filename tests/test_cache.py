"""Tests for edinet_mcp._cache."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from edinet_mcp._cache import DiskCache

if TYPE_CHECKING:
    from pathlib import Path


class TestDiskCache:
    def test_put_and_get_json(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        cache.put_json("ns", {"k": "v"}, {"data": 42})
        result = cache.get_json("ns", {"k": "v"})
        assert result == {"data": 42}

    def test_get_json_miss(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        assert cache.get_json("ns", {"k": "missing"}) is None

    def test_put_and_get_file(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        path = cache.put_file("ns", {"k": "v"}, b"hello", suffix=".txt")
        assert path.read_bytes() == b"hello"

        result = cache.get_file("ns", {"k": "v"}, suffix=".txt")
        assert result is not None
        assert result.read_bytes() == b"hello"

    def test_get_file_miss(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        assert cache.get_file("ns", {"k": "missing"}) is None

    def test_clear(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        cache.put_json("ns", {"k": "v"}, {"data": 1})
        cache.clear()
        assert cache.get_json("ns", {"k": "v"}) is None

    def test_file_permissions(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        path = cache.put_json("ns", {"k": "v"}, {"data": 1})
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600


class TestCacheTTL:
    def test_json_within_max_age(self, tmp_path: Path) -> None:
        """Cached JSON within max_age is returned."""
        cache = DiskCache(tmp_path)
        cache.put_json("ns", {"k": "v"}, {"data": 1})
        result = cache.get_json("ns", {"k": "v"}, max_age=3600)
        assert result == {"data": 1}

    def test_json_expired(self, tmp_path: Path) -> None:
        """Expired JSON cache returns None."""
        cache = DiskCache(tmp_path)
        path = cache.put_json("ns", {"k": "v"}, {"data": 1})
        # Backdate the file modification time by 2 hours
        old_time = time.time() - 7200
        os.utime(path, (old_time, old_time))

        result = cache.get_json("ns", {"k": "v"}, max_age=3600)
        assert result is None

    def test_json_no_max_age_never_expires(self, tmp_path: Path) -> None:
        """Without max_age, cache never expires."""
        cache = DiskCache(tmp_path)
        path = cache.put_json("ns", {"k": "v"}, {"data": 1})
        old_time = time.time() - 365 * 24 * 3600  # 1 year ago
        os.utime(path, (old_time, old_time))

        result = cache.get_json("ns", {"k": "v"})
        assert result == {"data": 1}

    def test_file_within_max_age(self, tmp_path: Path) -> None:
        """Cached file within max_age is returned."""
        cache = DiskCache(tmp_path)
        cache.put_file("ns", {"k": "v"}, b"data", suffix=".bin")
        result = cache.get_file("ns", {"k": "v"}, suffix=".bin", max_age=3600)
        assert result is not None

    def test_file_expired(self, tmp_path: Path) -> None:
        """Expired file cache returns None."""
        cache = DiskCache(tmp_path)
        path = cache.put_file("ns", {"k": "v"}, b"data", suffix=".bin")
        old_time = time.time() - 7200
        os.utime(path, (old_time, old_time))

        result = cache.get_file("ns", {"k": "v"}, suffix=".bin", max_age=3600)
        assert result is None


class TestCorruptCache:
    """A corrupt JSON cache entry must behave as a miss, not crash forever."""

    def test_corrupt_json_treated_as_miss_and_removed(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        path = cache.put_json("filings", {"date": "2026-07-17"}, {"ok": True})
        path.write_text("{not valid json", encoding="utf-8")

        assert cache.get_json("filings", {"date": "2026-07-17"}) is None
        # The poisoned entry is deleted so the next fetch can repopulate it
        assert not path.exists()

    def test_valid_json_still_returned(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        cache.put_json("filings", {"date": "2026-07-17"}, {"ok": True})
        assert cache.get_json("filings", {"date": "2026-07-17"}) == {"ok": True}


class TestAtomicWrites:
    def test_no_partial_file_visible_at_final_path(self, tmp_path: Path) -> None:
        """put_json must write via a temp file + atomic replace, so the
        final path never holds partial data (no .tmp residue either)."""
        cache = DiskCache(tmp_path)
        path = cache.put_json("ns", {"k": 1}, {"a": 1})
        assert path.exists()
        leftovers = [p for p in path.parent.iterdir() if p.name != path.name]
        assert leftovers == []

    def test_file_permissions_restricted(self, tmp_path: Path) -> None:
        cache = DiskCache(tmp_path)
        path = cache.put_file("docs", {"k": 1}, b"data", suffix=".zip")
        assert (path.stat().st_mode & 0o777) == 0o600

    def test_symlink_target_not_followed(self, tmp_path: Path) -> None:
        """A pre-planted symlink at the cache path must not cause writes
        through to the symlink target."""
        cache = DiskCache(tmp_path)
        victim = tmp_path / "victim.txt"
        victim.write_text("original")
        # Plant a symlink where the cache entry would go
        expected = cache.put_file("docs", {"k": 2}, b"probe", suffix=".zip")
        expected.unlink()
        expected.symlink_to(victim)
        cache.put_file("docs", {"k": 2}, b"overwritten", suffix=".zip")
        assert victim.read_text() == "original"
