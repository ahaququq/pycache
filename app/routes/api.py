"""API routes: JSON endpoints used by the admin UI."""
from __future__ import annotations

import time
from flask import Blueprint, jsonify, request, Response, stream_with_context

from ..downloader import download, head
from ..db import db
from ..sources import sources
from ..tracker import get_tracker

api = Blueprint("api", __name__)

tracker = get_tracker()


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
    
    # Update DB with probe result
    if result.ok:
        db.execute(
            """INSERT INTO files (source_id, local_path, remote_url, exists_upstream, unavailable, unavailable_reason, last_checked)
            VALUES (?, ?, ?, 1, 0, NULL, datetime('now'))
            ON CONFLICT(source_id, local_path) DO UPDATE SET
            exists_upstream=1, unavailable=0, unavailable_reason=NULL, last_checked=datetime('now')""",
            (source_id, local_path, remote_url),
        )
    else:
        # File is listed but unavailable
        error_reason = result.error or f"HTTP {result.status}"
        db.execute(
            """INSERT INTO files (source_id, local_path, remote_url, exists_upstream, unavailable, unavailable_reason, last_checked)
            VALUES (?, ?, ?, 0, 1, ?, datetime('now'))
            ON CONFLICT(source_id, local_path) DO UPDATE SET
            exists_upstream=0, unavailable=1, unavailable_reason=?, last_checked=datetime('now')""",
            (source_id, local_path, remote_url, error_reason, error_reason),
        )
    db._conn().commit()
    
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
            "unavailable_reason": result.error if not result.ok else None
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
    
    # Get source name for tracking
    source_row = db.fetchone("SELECT name FROM sources WHERE id=?", (source_id,))
    source_name = source_row["name"] if source_row else f"source_{source_id}"
    
    result = download(remote_url, local_path=local_path, source_name=source_name)
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


@api.route("/tracker/stream")
def tracker_stream():
    """Server-Sent Events stream for live tracker events."""
    def event_stream():
        queue = []
        
        def on_event(event):
            queue.append(event.to_sse())
        
        tracker.subscribe(on_event)
        try:
            # Send recent events first
            for event in tracker.get_events(limit=50):
                yield event.to_sse()
            
            # Then stream new events
            while True:
                if queue:
                    yield queue.pop(0)
                else:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
                    time.sleep(1)
        finally:
            tracker.unsubscribe(on_event)
    
    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@api.route("/tracker/events")
def tracker_events():
    """Get recent tracker events as JSON."""
    event_types = request.args.getlist("type")
    limit = request.args.get("limit", 100, type=int)
    events = tracker.get_events(limit=limit, event_types=event_types if event_types else None)
    return jsonify([e.to_dict() for e in events])


@api.route("/tracker/stats")
def tracker_stats():
    """Get tracker statistics."""
    return jsonify(tracker.get_event_counts())


@api.route("/sources/reload", methods=["POST"])
def reload_sources():
    sources.reload()
    return jsonify({"ok": True})


@api.route("/modules/reload", methods=["POST"])
def reload_modules():
    from ..modules._loader import registry
    registry.reload_all()
    sources.reload()
    return jsonify({"ok": True})