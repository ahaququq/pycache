#!/bin/bash
# Entrypoint for the cache server container.
# Starts nginx (foreground) and gunicorn (background).

set -euo pipefail

# Config from env
CACHE_DIR="${CACHE_DIR:-/app/cache}"
DATA_DIR="${DATA_DIR:-/app/data}"
MODULES_DIR="${MODULES_DIR:-/app/modules}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-4}"
THREADS="${THREADS:-2}"

echo "=== Cache Server Starting ==="
echo "Cache dir: $CACHE_DIR"
echo "Data dir: $DATA_DIR"
echo "Modules dir: $MODULES_DIR"
echo "Gunicorn: $HOST:$PORT ($WORKERS workers, $THREADS threads)"

# Ensure directories exist
mkdir -p "$CACHE_DIR" "$DATA_DIR" "$MODULES_DIR"

# Initialize database if needed (the app does this on import, but we can
# also run a quick check here)
python3 -c "
import sys
sys.path.insert(0, '/app')
from app.db import db
db.init()
print('Database initialized.')
"

# Start gunicorn in background
echo "Starting gunicorn..."
cd /app
exec gunicorn \
    --bind "$HOST:$PORT" \
    --workers "$WORKERS" \
    --threads "$THREADS" \
    --worker-class gthread \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    wsgi:app &
GUNICORN_PID=$!

# Give gunicorn a moment to start
sleep 2

# Start nginx in foreground (pid 1)
echo "Starting nginx..."
exec nginx -g "daemon off;"