"""Upstream download helper.

Resolves redirect chains and downloads the *final* payload, never a redirect
page. Used both by the request handler and by modules that want to fetch
something themselves.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

from . import cache as cache_mod
from .config import MAX_REDIRECTS, UPSTREAM_TIMEOUT, UPSTREAM_USER_AGENT
from .doh import get_doh_session

log = logging.getLogger("download")

# Use DoH-enabled session for DNS resolution
_SESSION = get_doh_session()
_SESSION.headers["User-Agent"] = UPSTREAM_USER_AGENT
_SESSION.max_redirects = MAX_REDIRECTS
# Allow the session to follow redirects ourselves so we can inspect each hop.
_SESSION.allow_redirects = False


@dataclass
class DownloadResult:
    ok: bool = False
    status: int = 0
    final_url: str = ""
    content_type: str = ""
    content_length: Optional[int] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    error: Optional[str] = None
    cached_path: Optional[str] = None
    bytes_written: int = 0
    redirected: bool = False


def _is_redirect(status: int) -> bool:
    return status in (301, 302, 303, 307, 308)


def head(url: str, timeout: Optional[int] = None) -> DownloadResult:
    """Probe a URL (HEAD) to learn size / existence without downloading."""
    res = DownloadResult()
    current = url
    seen = 0
    try:
        resp = _SESSION.head(current, timeout=timeout or UPSTREAM_TIMEOUT, allow_redirects=True)
        # requests followed redirects for us; reconstruct final url from history.
        if resp.history:
            res.redirected = True
            current = resp.url
        res.status = resp.status_code
        res.final_url = resp.url
        res.content_type = resp.headers.get("content-type", "")
        cl = resp.headers.get("content-length")
        res.content_length = int(cl) if cl and cl.isdigit() else None
        res.etag = resp.headers.get("etag")
        res.last_modified = resp.headers.get("last-modified")
        res.ok = resp.status_code == 200
        if resp.status_code >= 400:
            res.error = f"upstream returned {resp.status_code}"
            log.warning("HEAD probe failed for %s: %s", url, res.error)
    except requests.RequestException as exc:
        res.ok = False
        res.error = str(exc)
        log.error("HEAD probe exception for %s: %s", url, exc)
    return res


def download(url: str, timeout: Optional[int] = None) -> DownloadResult:
    """Download ``url``, following redirects, caching the final payload.

    Returns a DownloadResult. On success ``cached_path`` points at the cached
    file and ``bytes_written`` is its size.
    """
    res = DownloadResult()
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        try:
            resp = _SESSION.get(current, timeout=timeout or UPSTREAM_TIMEOUT, stream=True)
        except requests.RequestException as exc:
            res.ok = False
            res.error = str(exc)
            log.error("Download exception for %s: %s", current, exc)
            return res
        res.status = resp.status_code
        res.final_url = resp.url
        res.content_type = resp.headers.get("content-type", "")
        cl = resp.headers.get("content-length")
        res.content_length = int(cl) if cl and cl.isdigit() else None
        res.etag = resp.headers.get("etag")
        res.last_modified = resp.headers.get("last-modified")
        if _is_redirect(resp.status_code):
            location = resp.headers.get("location")
            res.redirected = True
            resp.close()
            if not location:
                res.ok = False
                res.error = "redirect without Location header"
                log.warning("Redirect without Location header for %s", current)
                return res
            current = urljoin(current, location)
            log.debug("Redirect: %s -> %s", current, location)
            continue
        if resp.status_code >= 400:
            resp.close()
            res.ok = False
            res.error = f"upstream returned {resp.status_code}"
            log.warning("Upstream returned %s for %s", resp.status_code, current)
            return res
        # Success: stream the body to a temp file then cache it atomically.
        try:
            hasher = hashlib.sha256()
            total = 0
            tmp_path = cache_mod.cache_path(current).with_suffix(
                cache_mod.cache_path(current).suffix + ".part"
            )
            # Ensure we have room before writing.
            estimated = res.content_length or 0
            cache_mod.ensure_space(estimated)
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    hasher.update(chunk)
                    total += len(chunk)
            resp.close()
            target = cache_mod.cache_path(current)
            os.replace(tmp_path, target)
            os.utime(target, None)
            res.cached_path = str(target)
            res.bytes_written = total
            res.ok = True
            res.content_length = total
            log.info("Downloaded %s (%d bytes) from %s", current, total, url)
            return res
        except OSError as exc:
            res.ok = False
            res.error = f"write failed: {exc}"
            log.error("Write failed for %s: %s", current, exc)
            return res
        finally:
            try:
                if "tmp_path" in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
    res.ok = False
    res.error = "too many redirects"
    log.error("Too many redirects for %s", url)
    return res


def fetch_bytes(url: str, timeout: Optional[int] = None) -> tuple[bytes, DownloadResult]:
    """Download without caching; returns (data, result)."""
    res = DownloadResult()
    current = url
    buf = bytearray()
    for _ in range(MAX_REDIRECTS + 1):
        try:
            resp = _SESSION.get(current, timeout=timeout or UPSTREAM_TIMEOUT, stream=True)
        except requests.RequestException as exc:
            res.ok = False
            res.error = str(exc)
            return bytes(buf), res
        res.status = resp.status_code
        res.final_url = resp.url
        res.content_type = resp.headers.get("content-type", "")
        if _is_redirect(resp.status_code):
            location = resp.headers.get("location")
            res.redirected = True
            resp.close()
            if not location:
                res.ok = False
                res.error = "redirect without Location"
                return bytes(buf), res
            current = urljoin(current, location)
            continue
        if resp.status_code >= 400:
            resp.close()
            res.ok = False
            res.error = f"upstream {resp.status_code}"
            return bytes(buf), res
        for chunk in resp.iter_content(chunk_size=1 << 16):
            if chunk:
                buf.extend(chunk)
        resp.close()
        res.ok = True
        res.content_length = len(buf)
        return bytes(buf), res
    res.ok = False
    res.error = "too many redirects"
    return bytes(buf), res