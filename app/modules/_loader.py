"""Module loader with isolation and crash protection.

Each module file in ``MODULES_DIR`` (except ``base.py``) is imported in its own
namespace. If importing a module raises, we catch it, record the failure, and
disable that module so a single bad file can never crash the server. A
background thread periodically reloads modules whose source file changed.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from ..base import ModuleBase, ModuleInfo, Item
from ..config import MODULES_DIR, MODULE_MAX_RELOAD_FAILURES, MODULE_RELOAD_INTERVAL
from ..db import db

log = logging.getLogger("modules")


def _inject_basenames(module) -> None:
    """Make ``ModuleBase`` / ``Item`` / ``ModuleInfo`` importable from inside
    a freshly loaded module file without any fragile package path."""
    if "app" not in sys.modules:
        sys.modules["app"] = __import__("app")
    from .. import base as _base
    module.__dict__["ModuleBase"] = ModuleBase
    module.__dict__["Item"] = Item
    module.__dict__["ModuleInfo"] = ModuleInfo
    module.__dict__["base"] = _base


class ModuleRegistry:
    """Holds all loaded modules, keyed by name."""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleBase] = {}
        self._failures: dict[str, int] = {}
        self._mtimes: dict[str, float] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._watchdog, name="module-watchdog", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    # -- loading ------------------------------------------------------------
    def _load_file(self, path: Path) -> Optional[ModuleBase]:
        name = path.stem
        if name == "base":
            return None
        spec = importlib.util.spec_from_file_location(
            f"_cache_modules.{name}", path
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        _inject_basenames(module)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 - we WANT to swallow module faults
            log.warning("module %s failed to import: %r", name, exc)
            return None

        cls = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, ModuleBase)
                and attr is not ModuleBase
            ):
                cls = attr
                break
        if cls is None:
            log.warning("module %s has no ModuleBase subclass", name)
            return None
        try:
            instance = cls()
        except Exception as exc:  # noqa: BLE001
            log.warning("module %s constructor raised: %r", name, exc)
            return None
        instance.name = name
        return instance

    def reload_all(self) -> dict[str, ModuleInfo]:
        """Re-scan the modules directory and load everything fresh."""
        result: dict[str, ModuleInfo] = {}
        with self._lock:
            seen: set[str] = set()
            if MODULES_DIR.exists():
                for path in sorted(MODULES_DIR.glob("*.py")):
                    if path.stem == "base":
                        continue
                    seen.add(path.stem)
                    inst = self._load_file(path)
                    if inst is None:
                        self._failures[path.stem] = self._failures.get(path.stem, 0) + 1
                        if self._failures[path.stem] >= MODULE_MAX_RELOAD_FAILURES:
                            self._modules.pop(path.stem, None)
                            result[path.stem] = ModuleInfo(
                                name=path.stem,
                                display_name=path.stem,
                                enabled=False,
                                healthy=False,
                                error=f"disabled after {MODULE_MAX_RELOAD_FAILURES} failures",
                                last_checked=time.strftime("%Y-%m-%d %H:%M:%S"),
                            )
                            continue
                        result[path.stem] = ModuleInfo(
                            name=path.stem,
                            display_name=path.stem,
                            enabled=False,
                            healthy=False,
                            error="import failed",
                            last_checked=time.strftime("%Y-%m-%d %H:%M:%S"),
                        )
                        continue
                    # Success: reset failure counter.
                    self._failures[path.stem] = 0
                    self._modules[path.stem] = inst
                    self._mtimes[path.stem] = path.stat().st_mtime
                    try:
                        n = len(inst.list_items() or [])
                    except Exception:  # noqa: BLE001
                        n = 0
                    result[path.stem] = ModuleInfo(
                        name=path.stem,
                        display_name=getattr(inst, "display_name", path.stem),
                        enabled=True,
                        healthy=True,
                        error=None,
                        last_checked=time.strftime("%Y-%m-%d %H:%M:%S"),
                        items=n,
                    )
            # Remove modules whose files are gone.
            for gone in list(self._modules):
                if gone not in seen:
                    self._modules.pop(gone, None)
                    self._failures.pop(gone, None)
                    self._mtimes.pop(gone, None)
            return result

    def _watchdog(self) -> None:
        while not self._stop.wait(MODULE_RELOAD_INTERVAL):
            try:
                changed = False
                if MODULES_DIR.exists():
                    for path in MODULES_DIR.glob("*.py"):
                        if path.stem == "base":
                            continue
                        try:
                            mtime = path.stat().st_mtime
                        except OSError:
                            continue
                        prev = self._mtimes.get(path.stem)
                        if prev is None or mtime > prev:
                            changed = True
                            break
                if changed:
                    log.info("module file changed; reloading all")
                    self.reload_all()
            except Exception as exc:  # noqa: BLE001
                log.warning("watchdog iteration failed: %r", exc)

    # -- accessors ----------------------------------------------------------
    def get(self, name: str) -> Optional[ModuleBase]:
        with self._lock:
            return self._modules.get(name)

    def all(self) -> dict[str, ModuleBase]:
        with self._lock:
            return dict(self._modules)

    def statuses(self) -> dict[str, ModuleInfo]:
        with self._lock:
            return {n: self._status(n, m) for n, m in self._modules.items()}

    def _status(self, name: str, mod: ModuleBase) -> ModuleInfo:
        try:
            n = len(mod.list_items() or [])
        except Exception:  # noqa: BLE001
            n = 0
        return ModuleInfo(
            name=name,
            display_name=getattr(mod, "display_name", name),
            enabled=True,
            healthy=True,
            error=None,
            last_checked=time.strftime("%Y-%m-%d %H:%M:%S"),
            items=n,
        )


# Singleton.
registry = ModuleRegistry()