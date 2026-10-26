"""Module system.

A *module* is a Python file placed in ``MODULES_DIR`` that exposes exactly one
class derived from :class:`ModuleBase`. Modules are the only thing that knows
how to turn a *local path* (e.g. ``gradle/8.5/gradle-8.5-bin.zip``) into a
*remote URL* and how to *enumerate* the files a source can provide.

Two kinds of module ship with the server:

* ``gradle`` - knows about services.gradle.org and can list every published
  Gradle distribution, so local Gradle installs can point at the cache.
* ``db`` - a generic "DB source": mappings stored in the ``mappings`` table.
  This is the quick & easy on-the-fly source the admin panel uses.

Modules are loaded in isolation (each gets its own import namespace) and any
fault in one module can never take the whole server down: failures are
counted, and after ``MODULE_MAX_RELOAD_FAILURES`` consecutive bad loads the
module is disabled until an admin reloads it.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import MODULES_DIR, MODULE_MAX_RELOAD_FAILURES, MODULE_RELOAD_INTERVAL

log = logging.getLogger("modules")


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------
@dataclass
class Item:
    """A file a source can provide."""

    local_path: str
    remote_url: str
    size: Optional[int] = None          # bytes, if known
    exists_upstream: Optional[bool] = None  # None = not probed yet
    description: str = ""


@dataclass
class ModuleInfo:
    """Metadata about a loaded module, surfaced to the admin panel."""

    name: str
    display_name: str
    enabled: bool
    healthy: bool
    error: Optional[str]
    last_checked: str
    items: int = 0


class ModuleBase:
    """Base class every module derives from.

    Subclasses set ``name`` (machine id, matches the filename without .py),
    optionally ``display_name``, and implement :meth:`list_items` and
    :meth:`resolve`.
    """

    name: str = "base"
    display_name: str = "Base Module"
    # Config dict, merged from DB row (if any) and the module's defaults.
    config: dict = field(default_factory=dict)

    # -- API to override -----------------------------------------------------
    def list_items(self) -> list[Item]:
        """Return every file this source can provide (upstream enumeration)."""
        return []

    def resolve(self, local_path: str) -> Optional[str]:
        """Map a local path to a remote URL, or None if unknown."""
        return None

    def probe(self, local_path: str) -> Optional[dict]:
        """Optionally probe upstream for a path; return metadata or None."""
        return None

    def get_config_schema(self) -> list[dict]:
        """Describe config fields for the admin UI: list of
        {key, label, type, default, help, secret}."""
        return []

    # -- helpers -------------------------------------------------------------
    def cfg(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)