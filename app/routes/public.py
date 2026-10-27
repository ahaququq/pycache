"""Public routes: cache proxy, info pages, health."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import unquote

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    send_file,
    stream_with_context,
)

from ..cache import cache_path, is_cached, touch, store
from ..config import CACHE_MAX_BYTES
from ..downloader import download, head
from ..db import db
from ..sources import sources
from ..tracker import get_tracker

log = logging.getLogger("routes.public")

public = Blueprint("public", __name__)

_tracker = get_tracker()


def _human(size: int) -> str:
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PiB"


# ---------------------------------------------------------------------------
# Cache proxy: /cache/<path:local_path>
# ---------------------------------------------------------------------------
@public.route("/cache/<path:local_path>")
def serve_cached(local_path: str) -> Response:
    local_path = unquote(local_path)
    res = sources.resolve(local_path)
    if res is None:
        abort(404, "no source provides this path")

    source_id, mod, remote_url = res
    cached_p = cache_path(remote_url)
    
    # Get source name for tracking
    source_row = db.fetchone("SELECT name FROM sources WHERE id=?", (source_id,))
    source_name = source_row["name"] if source_row else f"source_{source_id}"
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    
    # If cached, stream it.
    if cached_p.is_file():
        start_time = time.time()
        touch(remote_url)
        
        # Track serve start
        _tracker.serve_start(local_path, remote_url, source_name, client_ip)
        
        try:
            response = send_file(cached_p, as_attachment=True, download_name=Path(local_path).name)
            # We can't easily get bytes sent from send_file, so we'll use file size
            file_size = cached_p.stat().st_size
            duration = time.time() - start_time
            _tracker.serve_complete(local_path, file_size, duration, client_ip, from_cache=True)
            return response
        except Exception as exc:
            duration = time.time() - start_time
            _tracker.serve_error(local_path, str(exc), client_ip)
            raise

    # Not cached: fetch from upstream, store, then stream.
    _tracker.serve_start(local_path, remote_url, source_name, client_ip)
    download_start = time.time()
    result = download(remote_url, local_path=local_path, source_name=source_name)
    if not result.ok or result.cached_path is None:
        log.warning("download failed for %s: %s", remote_url, result.error)
        abort(502, f"upstream error: {result.error}")

    # Update DB: mark file cached.
    try:
        db.execute(
            "INSERT INTO files (source_id, local_path, remote_url, cached, cache_path, size, etag, last_modified, exists_upstream, last_checked) "
            "VALUES (?, ?, ?, 1, ?, ?, ?, ?, 1, datetime('now')) "
            "ON CONFLICT(source_id, local_path) DO UPDATE SET "
            "cached=1, cache_path=excluded.cache_path, size=excluded.size, etag=excluded.etag, "
            "last_modified=excluded.last_modified, exists_upstream=1, last_checked=datetime('now')",
            (
                source_id,
                local_path,
                remote_url,
                result.cached_path,
                result.bytes_written,
                result.etag,
                result.last_modified,
            ),
        )
        db._conn().commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("db update failed for %s: %r", local_path, exc)

    # Serve the newly cached file
    serve_start = time.time()
    try:
        response = send_file(cached_p, as_attachment=True, download_name=Path(local_path).name)
        file_size = result.bytes_written
        duration = time.time() - serve_start
        total_duration = time.time() - download_start
        _tracker.serve_complete(local_path, file_size, duration, client_ip, from_cache=False)
        return response
    except Exception as exc:
        duration = time.time() - serve_start
        _tracker.serve_error(local_path, str(exc), client_ip)
        raise


# ---------------------------------------------------------------------------
# Info pages: /info/by-path and /info/by-source
# ---------------------------------------------------------------------------
@public.route("/")
def root():
    return redirect(url_for("public.index"))

@public.route("/info")
def index():
    # Calculate total available upstream files
    total_upstream = 0
    for sid, inst in sources.instances().items():
        try:
            total_upstream += len(inst.list_items() or [])
        except Exception:
            pass
    return render_template("index.html", total_upstream=total_upstream)


@public.route("/info/by-path")
def by_path():
    # Get all available items from enabled sources
    all_items = []
    for sid, inst in sources.instances().items():
        try:
            items = inst.list_items() or []
        except Exception as exc:
            log.warning("source %d listing failed: %r", sid, exc)
            continue
        for item in items:
            all_items.append((sid, item))
    
    # Get cached/checked status from DB
    cached_files = {}
    rows = db.fetchall(
        """
        SELECT f.local_path, f.cached, f.size, f.exists_upstream,
               f.last_checked, f.remote_url
        FROM files f
        JOIN sources s ON s.id = f.source_id
        WHERE s.enabled=1
        """
    )
    for row in rows:
        cached_files[row["local_path"]] = row
    
    # Build combined rows: all available items + cache status
    combined_rows = []
    for sid, item in all_items:
        source = db.fetchone("SELECT name FROM sources WHERE id=?", (sid,))
        source_name = source["name"] if source else f"source_{sid}"
        
        cached = cached_files.get(item.local_path)
        if cached:
            cached_flag = cached["cached"]
            size = cached["size"]
            exists_upstream = cached["exists_upstream"]
            last_checked = cached["last_checked"]
            remote_url = cached["remote_url"]
        else:
            cached_flag = 0
            size = item.size
            exists_upstream = 1  # Available from source but not yet cached
            last_checked = None
            remote_url = item.remote_url
        
        combined_rows.append({
            "local_path": item.local_path,
            "remote_url": remote_url,
            "cached": cached_flag,
            "size": size,
            "exists_upstream": exists_upstream,
            "last_checked": last_checked,
            "source_name": source_name,
            "source_id": sid,
        })
    
    # Sort by path
    combined_rows.sort(key=lambda r: r["local_path"])
    
    return render_template(
        "by_path.html",
        rows=combined_rows,
        human=_human,
    )


@public.route("/info/by-source")
def by_source():
    # Get per-source stats including all available items
    source_rows = db.fetchall(
        "SELECT id, name, kind FROM sources WHERE enabled=1 ORDER BY name"
    )
    
    rows = []
    for src in source_rows:
        sid = src["id"]
        inst = sources.instances().get(sid)
        total_available = 0
        if inst:
            try:
                total_available = len(inst.list_items() or [])
            except Exception as exc:
                pass
        
        # Get cached count from DB
        cached_row = db.fetchone(
            "SELECT COUNT(*) AS cached FROM files WHERE source_id=? AND cached=1",
            (sid,),
        )
        cached = cached_row["cached"] if cached_row else 0
        
        rows.append({
            "id": sid,
            "name": src["name"],
            "kind": src["kind"],
            "total": total_available,
            "cached": cached,
            "upstream_only": total_available - cached,
        })
    
    return render_template(
        "by_source.html",
        rows=rows,
        human=_human,
    )


@public.route("/info/by-source/<int:source_id>")
def by_source_detail(source_id: int):
    source = db.fetchone("SELECT * FROM sources WHERE id=?", (source_id,))
    if not source:
        abort(404)
    
    # Get all available items from this source
    inst = sources.instances().get(source_id)
    if not inst:
        return render_template(
            "by_source_detail.html",
            source=source,
            rows=[],
            human=_human,
        )
    
    try:
        all_items = inst.list_items() or []
    except Exception as exc:
        log.warning("source %d listing failed: %r", source_id, exc)
        all_items = []
    
    # Get cached/checked status from DB
    cached_files = {}
    rows = db.fetchall(
        """
        SELECT local_path, cached, size, exists_upstream, last_checked, remote_url
        FROM files
        WHERE source_id=?
        """,
        (source_id,),
    )
    for row in rows:
        cached_files[row["local_path"]] = row
    
    # Build combined rows
    combined_rows = []
    for item in all_items:
        cached = cached_files.get(item.local_path)
        if cached:
            cached_flag = cached["cached"]
            size = cached["size"]
            exists_upstream = cached["exists_upstream"]
            last_checked = cached["last_checked"]
            remote_url = cached["remote_url"]
        else:
            cached_flag = 0
            size = item.size
            exists_upstream = 1  # Available from source but not yet cached
            last_checked = None
            remote_url = item.remote_url
        
        combined_rows.append({
            "local_path": item.local_path,
            "remote_url": remote_url,
            "cached": cached_flag,
            "size": size,
            "exists_upstream": exists_upstream,
            "last_checked": last_checked,
        })
    
    combined_rows.sort(key=lambda r: r["local_path"])
    
    return render_template(
        "by_source_detail.html",
        source=source,
        rows=combined_rows,
        human=_human,
    )


# ---------------------------------------------------------------------------
# Probe endpoint (used by admin to check upstream existence)
# ---------------------------------------------------------------------------
@public.route("/probe/<path:local_path>")
def probe(local_path: str):
    local_path = unquote(local_path)
    res = sources.resolve(local_path)
    if res is None:
        abort(404)
    source_id, mod, remote_url = res
    result = head(remote_url)
    return {
        "local_path": local_path,
        "remote_url": remote_url,
        "final_url": result.final_url,
        "status": result.status,
        "exists": result.ok,
        "size": result.content_length,
        "content_type": result.content_type,
        "etag": result.etag,
        "last_modified": result.last_modified,
        "error": result.error,
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@public.route("/health")
def health():
    return {"status": "ok", "cache_max_bytes": CACHE_MAX_BYTES}