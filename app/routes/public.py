"""Public routes: cache proxy, info pages, health."""
from __future__ import annotations

import logging
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

log = logging.getLogger("routes.public")

public = Blueprint("public", __name__)


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

    # If cached, stream it.
    if cached_p.is_file():
        touch(remote_url)
        return send_file(cached_p, as_attachment=True, download_name=Path(local_path).name)

    # Not cached: fetch from upstream, store, then stream.
    result = download(remote_url)
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

    return send_file(cached_p, as_attachment=True, download_name=Path(local_path).name)


# ---------------------------------------------------------------------------
# Info pages: /info/by-path and /info/by-source
# ---------------------------------------------------------------------------
@public.route("/")
def root():
    return redirect(url_for("public.index"))

@public.route("/info")
def index():
    return render_template("index.html")


@public.route("/info/by-path")
def by_path():
    rows = db.fetchall(
        """
        SELECT f.local_path, f.remote_url, f.cached, f.size, f.exists_upstream,
               f.last_checked, s.name AS source_name, s.id AS source_id
        FROM files f
        JOIN sources s ON s.id = f.source_id
        WHERE s.enabled=1
        ORDER BY f.local_path
        """
    )
    return render_template(
        "by_path.html",
        rows=rows,
        human=_human,
    )


@public.route("/info/by-source")
def by_source():
    # Get per-source stats
    rows = db.fetchall(
        """
        SELECT s.id, s.name, s.kind,
               COUNT(f.id) AS total,
               SUM(CASE WHEN f.cached=1 THEN 1 ELSE 0 END) AS cached,
               SUM(CASE WHEN f.exists_upstream=1 AND f.cached=0 THEN 1 ELSE 0 END) AS upstream_only
        FROM sources s
        LEFT JOIN files f ON f.source_id = s.id
        WHERE s.enabled=1
        GROUP BY s.id
        ORDER BY s.name
        """
    )
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
    rows = db.fetchall(
        """
        SELECT local_path, remote_url, cached, size, exists_upstream, last_checked
        FROM files
        WHERE source_id=?
        ORDER BY local_path
        """,
        (source_id,),
    )
    return render_template(
        "by_source_detail.html",
        source=source,
        rows=rows,
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