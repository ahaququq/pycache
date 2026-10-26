"""Generic DB-backed source.

A source of kind ``db`` has no built-in knowledge of what it serves: every
file it can provide is described by a row in the ``mappings`` table
(``local_path`` -> ``remote_url``). This is the quick & easy way to add a
mapping from the admin panel without writing any code.

The module reads its mappings from the row whose ``source_id`` matches the
source this module is bound to (set by the registry when it pairs a source
with a module instance).
"""
from __future__ import annotations

import logging
from typing import Optional

# ModuleBase, Item, ModuleInfo are injected by the loader.

log = logging.getLogger("module.db")


class DbSourceModule(ModuleBase):
    name = "db"
    display_name = "Database mappings"

    def _get_config_dict(self) -> dict:
        """Safely get config as dict, handling dataclass Field."""
        try:
            return dict(self.config)
        except (TypeError, ValueError):
            return {}

    def _source_id(self) -> Optional[int]:
        return self._get_config_dict().get("source_id")

    def _mappings(self) -> list[dict]:
        sid = self._source_id()
        if sid is None:
            return []
        from ..db import db
        return db.fetchall(
            "SELECT local_path, remote_url, enabled FROM mappings "
            "WHERE source_id=? ORDER BY local_path",
            (sid,),
        )

    def list_items(self) -> list[Item]:
        items: list[Item] = []
        for row in self._mappings():
            if not row["enabled"]:
                continue
            items.append(
                Item(
                    local_path=row["local_path"],
                    remote_url=row["remote_url"],
                    description="",
                )
            )
        return items

    def resolve(self, local_path: str) -> Optional[str]:
        sid = self._source_id()
        if sid is None:
            return None
        from ..db import db
        row = db.fetchone(
            "SELECT remote_url FROM mappings WHERE source_id=? AND local_path=?",
            (sid, local_path),
        )
        return row["remote_url"] if row else None

    def add_mapping(self, local_path: str, remote_url: str) -> None:
        sid = self._source_id()
        if sid is None:
            raise RuntimeError("db source has no source_id")
        from ..db import db
        db.execute(
            "INSERT INTO mappings (source_id, local_path, remote_url) VALUES (?,?,?) "
            "ON CONFLICT(source_id, local_path) DO UPDATE SET remote_url=excluded.remote_url",
            (sid, local_path, remote_url),
        )
        db._conn().commit()

    def remove_mapping(self, local_path: str) -> None:
        sid = self._source_id()
        if sid is None:
            return
        from ..db import db
        db.execute("DELETE FROM mappings WHERE source_id=? AND local_path=?", (sid, local_path))
        db._conn().commit()

    def get_config_schema(self) -> list[dict]:
        return []