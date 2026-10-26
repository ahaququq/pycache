"""API routes: JSON endpoints used by the admin UI."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..downloader import download, head
from ..db import db
from ..sources import sources

api = Blueprint("api", __name__)


@api.route("/probe", methods=["POST"])
def probe():
    """Probe a local path: resolve via sources, then HEAD upstream."""
    data = request.get_json() or {}
    local_path = data.get("local_path", "").strip()
    if not local_path:
        return jsonify({"ok": False, "error": "local_path required"}), 400
    res = sources.resolve(local_path)
    if res is None:
        return jsonify({"ok": False, "error": "no source provides this path"}), 404
    source_id, mod, remote_url = res
    result = head(remote_url)
    return jsonify(
        {
            "ok": True,
            "local_path": local_path,
            "source_id": source_id,
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
    )


@api.route("/download", methods=["POST"])
def api_download():
    """Force-download a path into the cache."""
    data = request.get_json() or {}
    local_path = data.get("local_path", "").strip()
    if not local_path:
        return jsonify({"ok": False, "error": "local_path required"}), 400
    res = sources.resolve(local_path)
    if res is None:
        return jsonify({"ok": False, "error": "no source provides this path"}), 404
    source_id, mod, remote_url = res
    result = download(remote_url)
    if result.ok:
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
    return jsonify(
        {
            "ok": result.ok,
            "bytes": result.bytes_written,
            "error": result.error,
            "cached_path": result.cached_path,
        }
    )


@api.route("/sources/reload", methods=["POST"])
def reload_sources():
    sources.reload()
    return jsonify({"ok": True})


@api.route("/modules/reload", methods=["POST"])
def reload_modules():
    from ..modules.loader import registry
    registry.reload_all()
    sources.reload()
    return jsonify({"ok": True})