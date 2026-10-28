"""
Central configuration for the caching server.

All tunables live here so that the Docker image can be configured via
environment variables without touching any code.

See Also:
    docs/10-configuration.md: Complete configuration reference
    docs/01-installation.md: Environment variables in docker-compose.yml
    docs/06-doh-dns.md: DNS configuration
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    """Parse boolean from environment variable.

    Args:
        name: Environment variable name
        default: Default value if not set

    Returns:
        Parsed boolean value
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Parse integer from environment variable.

    Args:
        name: Environment variable name
        default: Default value if not set

    Returns:
        Parsed integer or default
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bytes(name: str, default: int) -> int:
    """Parse human-readable size from environment variable.

    Args:
        name: Environment variable name
        default: Default value in bytes

    Returns:
        Size in bytes. Supports suffixes K, M, G, T.
        Examples: '16G', '512M', '1024'
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    raw = raw.strip().upper()
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    if raw[-1] in units:
        try:
            return int(float(raw[:-1]) * units[raw[-1]])
        except ValueError:
            return default
    try:
        return int(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.environ.get("CACHE_DIR", str(APP_DIR / "cache")))
DATA_DIR = Path(os.environ.get("DATA_DIR", str(APP_DIR / "data")))
MODULES_DIR = Path("/app/app/modules")

DB_PATH = DATA_DIR / "cache_server.db"

# Ensure directories exist at import time (idempotent).
for _d in (CACHE_DIR, DATA_DIR, MODULES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Cache limits
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Cache limits
# ---------------------------------------------------------------------------
# Maximum total on-disk usage of the cache directory, in bytes.
CACHE_MAX_BYTES = _env_bytes("CACHE_MAX_BYTES", 16 * 1024**3)  # 16 GiB default
# When the cache grows past this fraction of the max, start evicting.
CACHE_EVICTION_THRESHOLD = float(os.environ.get("CACHE_EVICTION_THRESHOLD", "0.9"))
# How many bytes to free when evicting (LRU).
CACHE_EVICTION_TARGET = _env_bytes("CACHE_EVICTION_TARGET", 2 * 1024**3)  # 2 GiB
# Minimum space to keep free on the filesystem so the OS can still write.
CACHE_MIN_FREE = _env_bytes("CACHE_MIN_FREE", 512 * 1024**2)  # 512 MiB

# ---------------------------------------------------------------------------
# Network / upstream
# ---------------------------------------------------------------------------
UPSTREAM_TIMEOUT = _env_int("UPSTREAM_TIMEOUT", 120)
MAX_REDIRECTS = _env_int("MAX_REDIRECTS", 10)
# User agent used when probing / downloading upstream.
UPSTREAM_USER_AGENT = os.environ.get(
    "UPSTREAM_USER_AGENT", "cache-server/1.0 (+https://example.invalid)"
)

# ---------------------------------------------------------------------------
# HTTP server (Flask / gunicorn)
# ---------------------------------------------------------------------------
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = _env_int("PORT", 8000)
# When running behind nginx on the host, this is the public scheme/host.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

# ---------------------------------------------------------------------------
# Admin / auth
# ---------------------------------------------------------------------------
# Password hash parameters (scrypt via passlib-like fallback; we use hashlib
# directly to avoid extra deps).
# The admin password is stored hashed in the DB. On first run, when no admin
# user exists, the server only accepts connections from 127.0.0.1 / ::1 and
# offers a one-time setup endpoint to create the admin account.
ADMIN_COOKIE_NAME = "cache_admin"
ADMIN_COOKIE_MAX_AGE = _env_int("ADMIN_COOKIE_MAX_AGE", 86400 * 7)  # 7 days
# Number of random bytes used when generating the per-request CSRF token.
CSRF_TOKEN_LENGTH = 32

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------
# If a module raises during import, reload it this many times before giving up.
MODULE_MAX_RELOAD_FAILURES = _env_int("MODULE_MAX_RELOAD_FAILURES", 3)
# How often (seconds) the background reloader checks module files.
MODULE_RELOAD_INTERVAL = _env_int("MODULE_RELOAD_INTERVAL", 5)

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
DEBUG = _env_bool("DEBUG", False)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")