"""Flask application factory.

Wires together the DB, module registry, source manager, auth, and routes.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask

__version__ = "1.0.0"

from . import __version__
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

    # Init DB + module directory.
    db.init()
    MODULES_DIR.mkdir(parents=True, exist_ok=True)

    # Load modules, then sources.
    registry.reload_all()
    sources.reload()

    # Background watchdog for module file changes.
    registry.start()

    # Register blueprints / routes.
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