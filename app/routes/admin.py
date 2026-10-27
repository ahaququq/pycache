"""Admin routes: authentication, source management, module editor, cache control."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import unquote

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..auth import (
    ADMIN_COOKIE_MAX_AGE,
    ADMIN_COOKIE_NAME,
    get_secret,
    hash_password,
    make_csrf_token,
    sign_cookie,
    verify_cookie,
    verify_password,
)
from ..cache import CACHE_DIR, purge_all, stats
from ..config import CACHE_MAX_BYTES, MODULES_DIR
from ..db import db
from ..modules._loader import registry
from ..sources import sources

log = logging.getLogger("routes.admin")

admin = Blueprint("admin", __name__)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _get_admin():
    row = db.fetchone("SELECT id, username, pw_hash, pw_salt FROM admin_users LIMIT 1")
    return row


def _is_local(request) -> bool:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    return ip in ("127.0.0.1", "::1", "localhost")


def _require_admin():
    # If no admin exists yet, only localhost may access admin.
    admin_row = _get_admin()
    if admin_row is None:
        if not _is_local(request):
            abort(403, "Admin account not set up. Access from localhost to create it.")
        return None  # No login required during initial setup.

    # Otherwise check cookie.
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        return redirect(url_for("admin.login", next=request.path))
    secret = get_secret()
    user = verify_cookie(token, secret, ADMIN_COOKIE_MAX_AGE)
    if not user:
        resp = make_response(redirect(url_for("admin.login", next=request.path)))
        resp.set_cookie(ADMIN_COOKIE_NAME, "", max_age=0, path="/")
        return resp
    request.admin_user = user
    return None


@admin.before_request
def _auth_check():
    # Skip auth for the login/setup endpoints themselves.
    if request.path in ("/admin/login", "/admin/setup"):
        return None
    if request.path.startswith("/admin"):
        res = _require_admin()
        if res:
            return res


# ---------------------------------------------------------------------------
# Login / Setup
# ---------------------------------------------------------------------------
@admin.route("/login", methods=["GET", "POST"])
def login():
    admin_row = _get_admin()
    if admin_row is None:
        # First-time setup: create admin user.
        if request.method == "POST":
            user = request.form.get("username", "").strip()
            pw = request.form.get("password", "")
            pw2 = request.form.get("password2", "")
            if not user or not pw:
                flash("Username and password required.", "error")
            elif pw != pw2:
                flash("Passwords do not match.", "error")
            else:
                pw_hash, pw_salt = hash_password(pw)
                db.execute(
                    "INSERT INTO admin_users (username, pw_hash, pw_salt) VALUES (?, ?, ?)",
                    (user, pw_hash, pw_salt),
                )
                db._conn().commit()
                flash("Admin account created. Please log in.", "success")
                return redirect(url_for("admin.login"))
        return render_template("admin/setup.html")

    # If already logged in, redirect to dashboard
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if token:
        secret = get_secret()
        user = verify_cookie(token, secret, ADMIN_COOKIE_MAX_AGE)
        if user:
            return redirect(url_for("admin.dashboard"))

    # Normal login.
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        print(f'DEBUG: user={user!r}, pw_len={len(pw)}', flush=True)
        if user == admin_row["username"] and verify_password(
            pw, admin_row["pw_hash"], admin_row["pw_salt"]
        ):
            print('DEBUG: password verified OK', flush=True)
            secret = get_secret()
            token = sign_cookie(f"{user}|{int(time.time())}", secret)
            print(f'DEBUG: token={token[:50]}...', flush=True)
            resp = make_response(redirect(request.args.get("next") or url_for("admin.dashboard")))
            resp.set_cookie(
                ADMIN_COOKIE_NAME,
                token,
                max_age=ADMIN_COOKIE_MAX_AGE,
                httponly=True,
                secure=False,
                samesite="Lax",
                path="/",
            )
            print(f'DEBUG: Set-Cookie header present', flush=True)
            return resp
        print('DEBUG: password verify FAILED', flush=True)
        flash("Invalid credentials.", "error")
    return render_template("admin/login.html")


@admin.route("/logout")
def logout():
    resp = make_response(redirect(url_for("admin.login")))
    resp.set_cookie(ADMIN_COOKIE_NAME, "", max_age=0, path="/")
    return resp


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin.route("/")
def dashboard():
    cache_info = stats()
    module_statuses = registry.statuses()
    source_rows = db.fetchall("SELECT * FROM sources WHERE enabled=1 ORDER BY name")
    return render_template(
        "admin/dashboard.html",
        cache=cache_info,
        modules=module_statuses,
        sources=source_rows,
        human=lambda b: f"{b/1024**3:.2f} GiB" if b else "0 B",
    )


# ---------------------------------------------------------------------------
# Source management
# ---------------------------------------------------------------------------
@admin.route("/sources")
def list_sources():
    rows = db.fetchall("SELECT * FROM sources ORDER BY id")
    modules = registry.all()
    return render_template("admin/sources.html", sources=rows, modules=modules)


@admin.route("/sources/new", methods=["GET", "POST"])
def new_source():
    modules = registry.all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        kind = request.form.get("kind", "").strip()
        config = {}
        for key in request.form:
            if key.startswith("cfg_"):
                config[key[4:]] = request.form[key]
        if not name or not kind:
            flash("Name and kind are required.", "error")
        elif kind not in modules:
            flash("Unknown module kind.", "error")
        else:
            db.execute(
                "INSERT INTO sources (name, kind, config, enabled) VALUES (?, ?, ?, 1)",
                (name, kind, json.dumps(config)),
            )
            db._conn().commit()
            sources.reload()
            flash("Source created.", "success")
            return redirect(url_for("admin.list_sources"))
    return render_template("admin/source_form.html", source=None, modules=modules)


@admin.route("/sources/<int:source_id>/edit", methods=["GET", "POST"])
def edit_source(source_id: int):
    source = db.fetchone("SELECT * FROM sources WHERE id=?", (source_id,))
    if not source:
        abort(404)
    modules = registry.all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        kind = request.form.get("kind", "").strip()
        enabled = 1 if request.form.get("enabled") else 0
        config = {}
        for key in request.form:
            if key.startswith("cfg_"):
                config[key[4:]] = request.form[key]
        if not name or not kind:
            flash("Name and kind are required.", "error")
        elif kind not in modules:
            flash("Unknown module kind.", "error")
        else:
            db.execute(
                "UPDATE sources SET name=?, kind=?, config=?, enabled=? WHERE id=?",
                (name, kind, json.dumps(config), enabled, source_id),
            )
            db._conn().commit()
            sources.reload()
            flash("Source updated.", "success")
            return redirect(url_for("admin.list_sources"))
    # Pre-fill config
    try:
        config = json.loads(source["config"] or "{}")
    except json.JSONDecodeError:
        config = {}
    return render_template(
        "admin/source_form.html",
        source=source,
        modules=modules,
        config=config,
    )


@admin.route("/sources/<int:source_id>/delete", methods=["POST"])
def delete_source(source_id: int):
    db.execute("DELETE FROM sources WHERE id=?", (source_id,))
    db._conn().commit()
    sources.reload()
    flash("Source deleted.", "success")
    return redirect(url_for("admin.list_sources"))


# ---------------------------------------------------------------------------
# DB source mappings management (per source)
# ---------------------------------------------------------------------------
@admin.route("/sources/<int:source_id>/mappings")
def source_mappings(source_id: int):
    source = db.fetchone("SELECT * FROM sources WHERE id=?", (source_id,))
    if not source:
        abort(404)
    if source["kind"] != "db":
        abort(400, "Mappings only available for 'db' kind sources.")
    rows = db.fetchall(
        "SELECT * FROM mappings WHERE source_id=? ORDER BY local_path", (source_id,)
    )
    return render_template("admin/mappings.html", source=source, mappings=rows)


@admin.route("/sources/<int:source_id>/mappings/new", methods=["GET", "POST"])
def new_mapping(source_id: int):
    source = db.fetchone("SELECT * FROM sources WHERE id=?", (source_id,))
    if not source or source["kind"] != "db":
        abort(404)
    if request.method == "POST":
        local_path = request.form.get("local_path", "").strip()
        remote_url = request.form.get("remote_url", "").strip()
        if not local_path or not remote_url:
            flash("Both fields required.", "error")
        else:
            db.execute(
                "INSERT INTO mappings (source_id, local_path, remote_url, enabled) VALUES (?, ?, ?, 1)",
                (source_id, local_path, remote_url),
            )
            db._conn().commit()
            sources.reload()
            flash("Mapping added.", "success")
            return redirect(url_for("admin.source_mappings", source_id=source_id))
    return render_template("admin/mapping_form.html", source=source, mapping=None)


@admin.route("/sources/<int:source_id>/mappings/<int:mapping_id>/delete", methods=["POST"])
def delete_mapping(source_id: int, mapping_id: int):
    db.execute("DELETE FROM mappings WHERE id=? AND source_id=?", (mapping_id, source_id))
    db._conn().commit()
    sources.reload()
    flash("Mapping deleted.", "success")
    return redirect(url_for("admin.source_mappings", source_id=source_id))


# ---------------------------------------------------------------------------
# Module editor (in-browser code editor)
# ---------------------------------------------------------------------------
@admin.route("/modules")
def list_modules():
    statuses = registry.statuses()
    return render_template("admin/modules.html", modules=statuses)


@admin.route("/modules/<name>")
def view_module(name: str):
    mod = registry.get(name)
    path = MODULES_DIR / f"{name}.py"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return render_template(
        "admin/module_view.html",
        name=name,
        content=content,
        status=statuses.get(name) if (statuses := registry.statuses()) else None,
    )


@admin.route("/modules/<name>/edit", methods=["GET", "POST"])
def edit_module(name: str):
    path = MODULES_DIR / f"{name}.py"
    if request.method == "POST":
        content = request.form.get("content", "")
        # Validate syntax before saving
        try:
            compile(content, f"<module {name}>", "exec")
        except SyntaxError as exc:
            flash(f"Syntax error: {exc}", "error")
            return render_template("admin/module_edit.html", name=name, content=content)
        path.write_text(content, encoding="utf-8")
        registry.reload_all()
        sources.reload()
        flash("Module saved and reloaded.", "success")
        return redirect(url_for("admin.view_module", name=name))
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return render_template("admin/module_edit.html", name=name, content=content)


@admin.route("/modules/new", methods=["GET", "POST"])
def new_module():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        content = request.form.get("content", "")
        if not name or not name.isidentifier():
            flash("Invalid module name.", "error")
        elif (MODULES_DIR / f"{name}.py").exists():
            flash("Module already exists.", "error")
        else:
            try:
                compile(content, f"<module {name}>", "exec")
            except SyntaxError as exc:
                flash(f"Syntax error: {exc}", "error")
                return render_template("admin/module_edit.html", name=name, content=content)
            (MODULES_DIR / f"{name}.py").write_text(content, encoding="utf-8")
            registry.reload_all()
            sources.reload()
            flash("Module created.", "success")
            return redirect(url_for("admin.view_module", name=name))
    return render_template("admin/module_edit.html", name="", content="")


@admin.route("/modules/<name>/reload", methods=["POST"])
def reload_module(name: str):
    registry.reload_all()
    sources.reload()
    flash("All modules reloaded.", "success")
    return redirect(url_for("admin.view_module", name=name))


# ---------------------------------------------------------------------------
# Log viewer
# ---------------------------------------------------------------------------
@admin.route("/logs")
def logs():
    """View recent log entries."""
    page = request.args.get("page", 1, type=int)
    per_page = 100
    offset = (page - 1) * per_page
    
    level_filter = request.args.get("level", "")
    module_filter = request.args.get("module", "")
    
    where_clauses = []
    params = []
    
    if level_filter:
        where_clauses.append("level = ?")
        params.append(level_filter)
    if module_filter:
        where_clauses.append("module = ?")
        params.append(module_filter)
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # Get total count
    total_row = db.fetchone(f"SELECT COUNT(*) as count FROM log_entries {where_sql}", tuple(params))
    total = total_row["count"] if total_row else 0
    
    # Get log entries
    rows = db.fetchall(
        f"SELECT * FROM log_entries {where_sql} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        tuple(params + [per_page, offset]),
    )
    
    # Get available levels and modules for filters
    levels = [r["level"] for r in db.fetchall("SELECT DISTINCT level FROM log_entries ORDER BY level")]
    modules = [r["module"] for r in db.fetchall("SELECT DISTINCT module FROM log_entries ORDER BY module")]
    
    return render_template(
        "admin/logs.html",
        logs=rows,
        levels=levels,
        modules=modules,
        current_level=level_filter,
        current_module=module_filter,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=(total + per_page - 1) // per_page,
    )


@admin.route("/logs/clear", methods=["POST"])
def clear_logs():
    """Clear all log entries."""
    db.execute("DELETE FROM log_entries")
    db._conn().commit()
    flash("Log entries cleared.", "success")
    return redirect(url_for("admin.logs"))


# ---------------------------------------------------------------------------
# Cache control
# ---------------------------------------------------------------------------
@admin.route("/cache")
def cache_panel():
    info = stats()
    return render_template("admin/cache.html", cache=info)


@admin.route("/cache/purge", methods=["POST"])
def purge_cache():
    count = purge_all()
    # Also clear the DB cached flags
    db.execute("UPDATE files SET cached=0, cache_path=NULL")
    db._conn().commit()
    flash(f"Purged {count} cached files.", "success")
    return redirect(url_for("admin.cache_panel"))


@admin.route("/cache/config", methods=["GET", "POST"])
def cache_config():
    from ..config import CACHE_MAX_BYTES as CURRENT_MAX
    if request.method == "POST":
        # Can't change config at runtime without restart; just show message.
        flash("Cache size limit is set via CACHE_MAX_BYTES env var and requires restart.", "info")
        return redirect(url_for("admin.cache_config"))
    return render_template("admin/cache_config.html", max_bytes=CURRENT_MAX)