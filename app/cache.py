"""On-disk LRU cache with a hard byte limit.

The cache is a flat directory of files named by a SHA-256 of the canonical
remote URL (so collisions are effectively impossible and the name is stable).
Metadata (size, mtime, last access) is tracked in SQLite via the ``files``
table; the filesystem is the source of truth for *actual* bytes.

Eviction is LRU by last-access time. It runs on a best-effort basis before
every insert and is bounded so a single large download can never exhaust the
disk (we keep ``CACHE_MIN_FREE`` bytes free).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from .config import (
    CACHE_DIR,
    CACHE_EVICTION_TARGET,
    CACHE_EVICTION_THRESHOLD,
    CACHE_MAX_BYTES,
    CACHE_MIN_FREE,
)

log = logging.getLogger("cache")


def cache_name(remote_url: str) -> str:
    """Stable, collision-resistant filename for a remote URL."""
    h = hashlib.sha256(remote_url.encode("utf-8")).hexdigest()
    return h


def cache_path(remote_url: str) -> Path:
    return CACHE_DIR / cache_name(remote_url)


def dir_size(path: Path) -> int:
    """Total bytes of all regular files under ``path`` (non-recursive)."""
    total = 0
    try:
        for entry in path.iterdir():
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    except FileNotFoundError:
        pass
    return total


def free_space() -> int:
    try:
        st = os.statvfs(str(CACHE_DIR))
        return st.f_bavail * st.f_frsize
    except OSError:
        return 0


def _evict_once(target_bytes: int) -> int:
    """Evict least-recently-used files until we have freed ``target_bytes``.

    Returns the number of bytes actually freed.
    """
    freed = 0
    # Build candidate list: (atime, path, size). atime is updated on read.
    entries = []
    try:
        for entry in CACHE_DIR.iterdir():
            if not entry.is_file():
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            entries.append((st.st_atime, entry, st.st_size))
    except FileNotFoundError:
        return 0

    entries.sort(key=lambda t: t[0])  # oldest access first
    for atime, entry, size in entries:
        if freed >= target_bytes:
            break
        try:
            entry.unlink()
            freed += size
            log.debug("evicted %s (%d bytes)", entry.name, size)
        except OSError as exc:
            log.warning("failed to evict %s: %s", entry, exc)
    return freed


def ensure_space(required_bytes: int = 0) -> None:
    """Make room for ``required_bytes`` by evicting LRU entries.

    Honours both the configured max cache size and a floor of free filesystem
    space so the OS never runs out of room mid-write.
    """
    current = dir_size(CACHE_DIR)
    need_free = max(required_bytes, CACHE_MIN_FREE)
    # How much we must free to satisfy the max-size rule.
    over_max = current - CACHE_MAX_BYTES
    # How much we must free to keep the filesystem floor.
    free_now = free_space()
    over_floor = need_free - free_now if free_now > 0 else need_free
    target = max(0, over_max, over_floor)
    # If we are above the eviction threshold fraction, also trim a little extra
    # to get back under the threshold proactively.
    if CACHE_MAX_BYTES > 0 and current > CACHE_MAX_BYTES * CACHE_EVICTION_THRESHOLD:
        target = max(target, CACHE_EVICTION_TARGET)
    if target <= 0:
        return
    _evict_once(target)


def is_cached(remote_url: str) -> bool:
    return cache_path(remote_url).is_file()


def get_cached_bytes(remote_url: str) -> int:
    p = cache_path(remote_url)
    try:
        return p.stat().st_size
    except OSError:
        return 0


def touch(remote_url: str) -> None:
    """Update access time for LRU bookkeeping."""
    p = cache_path(remote_url)
    try:
        os.utime(p, None)
    except OSError:
        pass


def store(remote_url: str, data: bytes) -> Path:
    """Atomically write ``data`` to the cache and return its path."""
    ensure_space(len(data))
    target = cache_path(remote_url)
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        os.utime(target, None)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    return target


def remove(remote_url: str) -> bool:
    p = cache_path(remote_url)
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def purge_all() -> int:
    """Remove every cached file. Returns count removed."""
    removed = 0
    try:
        for entry in CACHE_DIR.iterdir():
            if entry.is_file():
                try:
                    entry.unlink()
                    removed += 1
                except OSError:
                    pass
    except FileNotFoundError:
        pass
    return removed


def stats() -> dict:
    return {
        "total_bytes": dir_size(CACHE_DIR),
        "max_bytes": CACHE_MAX_BYTES,
        "file_count": sum(1 for _ in CACHE_DIR.iterdir() if _.is_file()),
        "free_bytes": free_space(),
    }