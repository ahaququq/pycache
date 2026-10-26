"""Built-in Gradle distribution source.

Serves published Gradle ``-bin.zip`` distributions from services.gradle.org.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

# These symbols are injected by the loader
# from base import ModuleBase, Item

log = logging.getLogger("module.gradle")

INDEX_URL = "https://services.gradle.org/distributions/"
# Regex to match gradle-x.y-bin.zip
_VERSION_RE = re.compile(r"gradle-(\d+\.\d+(?:\.\d+)?(?:[-+].*)?)-bin\.zip")


class GradleModule(ModuleBase):
    name = "gradle"
    display_name = "Gradle Distributions"

    _cache: list[Item] = []
    _cache_ts: float = 0.0
    _cache_ttl: float = 300

    def _fetch_index(self) -> list[Item]:
        import requests
        try:
            resp = requests.get(INDEX_URL, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            log.warning("failed to fetch gradle index: %r", exc)
            return []
        
        items: list[Item] = []
        for m in _VERSION_RE.finditer(resp.text):
            version = m.group(1)
            # Map to expected local path structure
            local = f"gradle/{version}/gradle-{version}-bin.zip"
            remote = f"{INDEX_URL}gradle-{version}-bin.zip"
            items.append(Item(local_path=local, remote_url=remote, description=f"Gradle {version}"))
        
        # Deduplicate
        unique = {i.local_path: i for i in items}.values()
        return sorted(unique, key=lambda i: i.local_path, reverse=True)

    def list_items(self) -> list[Item]:
        now = time.time()
        if not self._cache or (now - self._cache_ts) > self._cache_ttl:
            self._cache = self._fetch_index()
            self._cache_ts = now
        return self._cache

    def resolve(self, local_path: str) -> Optional[str]:
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
        res = head(remote)
        return {
            "exists_upstream": res.ok,
            "size": res.content_length,
            "final_url": res.final_url
        }
