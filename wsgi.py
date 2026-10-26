#!/usr/bin/env python3
"""Entry point for the cache server (gunicorn target)."""
from __future__ import annotations

import os
import sys

# Ensure the app package is importable when run from this file.
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Allow direct python run for debugging (not for production).
    from app.config import HOST, PORT
    app.run(host=HOST, port=PORT, debug=True)