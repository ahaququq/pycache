"""Source manager.

A *source* is a row in the ``sources`` table: a name, a kind (the module
that backs it), and a JSON config blob. The manager turns each enabled source
row into a live :class:`ModuleBase` instance (by asking the registry for the
module named by ``kind``) and injects the source's id/config into it.

This is what lets a single Gradle module back many sources with different
index URLs, and what lets ``db`` sources be created on the fly.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from .base import ModuleBase
from .db import db
from .modules._loader import registry

log = logging.getLogger("sources")


class SourceManager:
    def __init__(self) -> None:
        self._instances: dict[int, ModuleBase] = {}  # source_id -> module instance
        self._by_path: dict[str, tuple[int, ModuleBase]] = {}  # local_path -> (source_id, inst)

    def reload(self) -> None:
        """Rebuild the instance map from the sources table."""
        rows = db.fetchall(
            "SELECT id, name, kind, config, enabled FROM sources WHERE enabled=1"
        )
        new_instances: dict[int, ModuleBase] = {}
        for row in rows:
            sid = row["id"]
            kind = row["kind"]
            mod = registry.get(kind)
            if mod is None:
                log.warning("source %d (%s) references unknown module %s", sid, row["name"], kind)
                continue
            try:
                config = json.loads(row["config"] or "{}")
            except json.JSONDecodeError:
                config = {}
            config["source_id"] = sid
            config["source_name"] = row["name"]
            # Copy per-source config into a fresh instance so concurrent
            # requests don't mutate the shared registry module.
            inst = mod.__class__()
            inst.name = mod.name
            inst.display_name = getattr(mod, "display_name", mod.name)
            inst.config = dict(getattr(mod, "config", {}))
            inst.config.update(config)
            new_instances[sid] = inst
        self._instances = new_instances
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._by_path = {}
        for sid, inst in self._instances.items():
            try:
                items = inst.list_items() or []
            except Exception as exc:  # noqa: BLE001
                log.warning("source %d listing failed: %r", sid, exc)
                continue
            for it in items:
                self._by_path[it.local_path] = (sid, inst)

    def resolve(self, local_path: str) -> Optional[tuple[int, ModuleBase, str]]:
        """Return (source_id, module, remote_url) for a local path, or None."""
        hit = self._by_path.get(local_path)
        if hit:
            sid, inst = hit
            remote = inst.resolve(local_path)
            if remote:
                return sid, inst, remote
        # Fall back to a per-source resolve in case the path wasn't enumerated.
        for sid, inst in self._instances.items():
            remote = inst.resolve(local_path)
            if remote:
                return sid, inst, remote
        return None

    def all_items(self) -> list[tuple[int, ModuleBase, object]]:
        out = []
        for sid, inst in self._instances.items():
            try:
                items = inst.list_items() or []
            except Exception:  # noqa: BLE001
                continue
            for it in items:
                out.append((sid, inst, it))
        return out

    def instances(self) -> dict[int, ModuleBase]:
        return dict(self._instances)


# Singleton.
sources = SourceManager()