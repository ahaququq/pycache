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
               f.unavailable, f.unavailable_reason,
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
            cached_dict = dict(cached) if not isinstance(cached, dict) else cached
            cached_flag = cached_dict["cached"]
            size = cached_dict["size"]
            exists_upstream = cached_dict["exists_upstream"]
            unavailable = cached_dict.get("unavailable", 0)
            unavailable_reason = cached_dict.get("unavailable_reason")
            last_checked = cached_dict["last_checked"]
            remote_url = cached_dict["remote_url"]
        else:
            cached_flag = 0
            size = item.size
            exists_upstream = 1  # Available from source but not yet cached
            unavailable = 0
            unavailable_reason = None
            last_checked = None
            remote_url = item.remote_url
        
        combined_rows.append({
            "local_path": item.local_path,
            "remote_url": remote_url,
            "cached": cached_flag,
            "size": size,
            "exists_upstream": exists_upstream,
            "unavailable": unavailable,
            "unavailable_reason": unavailable_reason,
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
        SELECT local_path, cached, size, exists_upstream,
               unavailable, unavailable_reason,
               last_checked, remote_url
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
            cached_dict = dict(cached) if not isinstance(cached, dict) else cached
            cached_flag = cached_dict["cached"]
            size = cached_dict["size"]
            exists_upstream = cached_dict["exists_upstream"]
            unavailable = cached_dict.get("unavailable", 0)
            unavailable_reason = cached_dict.get("unavailable_reason")
            last_checked = cached_dict["last_checked"]
            remote_url = cached_dict["remote_url"]
        else:
            cached_flag = 0
            size = item.size
            exists_upstream = 1  # Available from source but not yet cached
            unavailable = 0
            unavailable_reason = None
            last_checked = None
            remote_url = item.remote_url
        
        combined_rows.append({
            "local_path": item.local_path,
            "remote_url": remote_url,
            "cached": cached_flag,
            "size": size,
            "exists_upstream": exists_upstream,
            "unavailable": unavailable,
            "unavailable_reason": unavailable_reason,
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
        "unavailable_reason": result.error if not result.ok else None
    }


# ---------------------------------------------------------------------------
# Documentation page
# ---------------------------------------------------------------------------
@public.route("/docs/<path:doc_path>")
def serve_doc(doc_path: str) -> Response:
    from pathlib import Path
    from flask import current_app, abort, Response
    
    docs_dir = Path(current_app.config.get(
        "DOCS_DIR", str(Path(__file__).parent.parent.parent / "docs")
    ))
    
    doc_file = (docs_dir / doc_path).resolve()
    docs_dir_resolved = docs_dir.resolve()
    
    if not doc_file.is_file():
        abort(404, f"documentation not found: {doc_path}")
    
    if not str(doc_file).startswith(str(docs_dir_resolved)):
        abort(404, "invalid documentation path")
    
    try:
        md_content = doc_file.read_text(encoding="utf-8")
    except Exception:
        abort(500, f"failed to read documentation: {doc_path}")
    
    # Basic markdown to HTML conversion
    lines = md_content.split("\n")
    html_parts = []
    i = 0
    in_list = False
    in_table = False
    table_rows = []
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            if in_table and table_rows:
                html_parts.append("</table>")
                in_table = False
                table_rows = []
            i += 1
            continue
        
        header_level = 0
        if stripped.startswith("# "):
            header_level = 1
            content = stripped[2:]
        elif stripped.startswith("## "):
            header_level = 2
            content = stripped[3:]
        elif stripped.startswith("### "):
            header_level = 3
            content = stripped[4:]
        else:
            content = stripped
        
        if header_level == 1:
            if in_list: html_parts.append("</ul>"); in_list = False
            if in_table and table_rows: html_parts.append("</table>"); in_table = False; table_rows = []
            html_parts.append("<h1>" + content + "</h1>")
        elif header_level == 2:
            if in_list: html_parts.append("</ul>"); in_list = False
            if in_table and table_rows: html_parts.append("</table>"); in_table = False; table_rows = []
            html_parts.append("<h2>" + content + "</h2>")
        elif header_level == 3:
            if in_list: html_parts.append("</ul>"); in_list = False
            if in_table and table_rows: html_parts.append("</table>"); in_table = False; table_rows = []
            html_parts.append("<h3>" + content + "</h3>")
        else:
            if '|' in content and content.count("|") >= 2 and i + 1 < len(lines) and "|---" in lines[i+1]:
                in_table = True
                rows = [c.strip() for c in content.split("|") if c.strip()]
                table_rows = [rows]
                i += 1
                continue
            elif in_table:
                rows = [c.strip() for c in content.split("|") if c.strip()]
                if rows:
                    table_rows.append(rows)
                if i + 1 >= len(lines) or (lines[i+1].strip() and not "|" in lines[i+1]):
                    html_parts.append("<table>")
                    for trows in table_rows:
                        html_parts.append("<tr>")
                        for cell in trows:
                            html_parts.append("<td>" + cell + "</td>")
                        html_parts.append("</tr>")
                    html_parts.append("</table>")
                    in_table = False
                    table_rows = []
            else:
                html_parts.append("<p>" + content + "</p>")
        
        i += 1
    
    if in_list: html_parts.append("</ul>")
    if in_table and table_rows: html_parts.append("</table>")
    html_body = "".join(html_parts)
    
    page_html = "<!DOCTYPE html><html lang=\"en\" data-theme=\"auto\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><link rel=\"stylesheet\" href=\"/static/css/main.css\"></head><body><header class=\"topbar\"><div class=\"topbar-left\"><a href=\"/\" class=\"brand\">Cache Server</a><nav class=\"breadcrumb\"><span><a href=\"/\">Home</a></span><span>/</span><span>Documentation</span></nav></div><div class=\"topbar-right\"><a href=\"/admin/dashboard\" class=\"btn\">Dashboard</a><a href=\"/admin/logout\" class=\"btn btn-outline\">Logout</a></div></header><main class=\"container\"><div class=\"content\">" + html_body + "</div></main><footer class=\"footer\"><span>Cache Server</span></footer></body></html>"
    
    return Response(page_html, mimetype="text/html")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@public.route("/health")
def health():
    return {"status": "ok", "cache_max_bytes": CACHE_MAX_BYTES}