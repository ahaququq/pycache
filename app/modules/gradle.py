"""Built-in Gradle distribution source.

Serves every published Gradle ``-bin.zip`` from services.gradle.org so that
local Gradle environments can be pointed at this cache:

    GRADLE_USER_HOME=/path/to/cache/gradle ./gradlew ...

The module enumerates the upstream index page and maps local paths of the
form ``gradle/<version>/gradle-<version>-bin.zip`` to the canonical remote URL.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

# ModuleBase, Item, ModuleInfo are injected by the loader.
# from base import ModuleBase, Item

log = logging.getLogger("module.gradle")

INDEX_URL = "https://services.gradle.org/distributions/"
_VERSION_RE = re.compile(r"gradle-(\d+\.\d+(?:\.\d+)?(?:[-+].*)?)-bin\.zip")


class GradleModule(ModuleBase):
    name = "gradle"
    display_name = "Gradle Distributions"

    # Cache the parsed list for a while; the index changes rarely.
    _cache: list[Item] = []
    _cache_ts: float = 0.0
    _cache_ttl: float = 300  # 5 minutes

    # -- helpers ------------------------------------------------------------
    def _fetch_index(self) -> list[Item]:
        import requests

        try:
            resp = requests.get(INDEX_URL, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to fetch gradle index: %r", exc)
            return []
        items: list[Item] = []
        for m in _VERSION_RE.finditer(resp.text):
            version = m.group(1)
            local = f"gradle/{version}/gradle-{version}-bin.zip"
            remote = f"{INDEX_URL}gradle-{version}-bin.zip"
            items.append(Item(local_path=local, remote_url=remote, description=f"Gradle {version}"))
        # Deduplicate and sort newest-first.
        seen: set[str] = set()
        unique: list[Item] = []
        for it in items:
            if it.local_path in seen:
                continue
            seen.add(it.local_path)
            unique.append(it)
        unique.sort(key=lambda i: i.local_path, reverse=True)
        return unique

    # -- ModuleBase API -----------------------------------------------------
    def list_items(self) -> list[Item]:
        now = time.time()
        if self._cache and now - self._cache_ts < self._cache_ttl:
            return self._cache
        fresh = self._fetch_index()
        if fresh:
            self._cache = fresh
            self._cache_ts = now
        return self._cache

    def resolve(self, local_path: str) -> Optional[str]:
        # Accept both "gradle/X/gradle-X-bin.zip" and bare "gradle-X-bin.zip".
        m = _VERSION_RE.search(local_path)
        if not m:
            return None
        version = m.group(1)
        return f"{INDEX_URL}gradle-{version}-bin.zip"

    def probe(self, local_path: str) -> Optional[dict]:
        from ..downloader import head

        remote = self.resolve(local_path)
        if not remote:
            return None
        result = head(remote)
        return {
            "exists_upstream": result.ok,
            "size": result.content_length,
            "content_type": result.content_type,
            "etag": result.etag,
            "last_modified": result.last_modified,
            "final_url": result.final_url,
        }

    def get_config_schema(self) -> list[dict]:
        return [
            {
                "key": "index_url",
                "label": "Index URL",
                "type": "text",
                "default": INDEX_URL,
                "help": "Base URL of the Gradle distributions index page.",
            },
        ]