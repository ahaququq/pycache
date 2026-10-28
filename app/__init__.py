"""
Flask application factory.

Wires together the DB, module registry, source manager, auth, and routes.

See Also:
    docs/00-overview.md: Project architecture overview
    docs/01-installation.md: Installation and setup
    docs/03-admin-panel.md: Admin panel features
    docs/04-live-tracker.md: Live tracker and SSE
    docs/08-log-viewer.md: Log viewer and DBLogHandler
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, g
from werkzeug.middleware.proxy_fix import ProxyFix

__version__ = "1.0.0"
from .auth import get_secret
from .cache import purge_all
from .config import (
    BASE_DIR,
    CACHE_DIR,
    DATA_DIR,
    HOST,
    LOG_LEVEL,
    MODULES_DIR,
    PORT,
)
from .db import db
from .modules._loader import registry
from .sources import sources


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "app" / "templates"),
        static_folder=str(BASE_DIR / "app" / "static"),
    )
    app.config["SECRET_KEY"] = get_secret()
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # admin uploads capped

    logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    app.logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # Install database logging handler
    from .log_handler import DBLogHandler
    db_handler = DBLogHandler()
    db_handler.setLevel(logging.INFO)  # Log INFO and above to DB
    db_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logging.getLogger().addHandler(db_handler)
    app.logger.addHandler(db_handler)

    # Init DB + module directory.
    db.init()
    MODULES_DIR.mkdir(parents=True, exist_ok=True)

    # Load modules, then sources.
    registry.reload_all()
    sources.reload()

    # Background watchdog for module file changes.
    registry.start()

    # If running behind a reverse proxy (or in this case, Nginx proxying to Flask),
    # ensure Flask handles the headers correctly.
    # We trust the proxy since it's the same container, but Nginx should
    # pass 'X-Forwarded-Proto' etc.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Generate CSP nonce for each request
    @app.before_request
    def generate_csp_nonce():
        import secrets
        g.csp_nonce = secrets.token_urlsafe(16)

    # Add CSP nonce to all templates
    @app.context_processor
    def inject_csp_nonce():
        return dict(csp_nonce=getattr(g, 'csp_nonce', ''))

    # Add CSP header with nonce
    @app.after_request
    def add_csp_header(response):
        nonce = getattr(g, 'csp_nonce', '')
        if nonce:
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-eval' 'nonce-" + nonce + "' https://cdn.jsdelivr.net blob:; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "font-src 'self' data: https://cdn.jsdelivr.net; "
                "connect-src 'self'; "
                "worker-src 'self' blob:;"
            )
            response.headers['Content-Security-Policy'] = csp
        return response

    # Register blueprints
    from .routes.public import public
    from .routes.admin import admin
    from .routes.api import api
    app.register_blueprint(public)
    app.register_blueprint(admin, url_prefix="/admin")
    app.register_blueprint(api, url_prefix="/api")

    # Teardown: nothing to do, but keep the hook for future use.
    @app.teardown_appcontext
    def _close(exc):
        pass

    # Expose helpers to templates.
    app.jinja_env.globals["app_version"] = __version__
    app.jinja_env.globals["cache_stats"] = lambda: _safe_stats()

    @app.template_filter("human_bytes")
    def human_bytes_filter(b):
        try:
            b = int(b)
        except (TypeError, ValueError):
            return "—"
        for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PiB"

    return app


def _safe_stats():
    from .cache import stats
    try:
        return stats()
    except Exception:
        return {"total_bytes": 0, "max_bytes": 0, "file_count": 0, "free_bytes": 0}