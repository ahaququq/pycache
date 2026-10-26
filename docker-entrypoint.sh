#!/bin/bash
set -euo pipefail

# Ensure directories exist and are owned by app user
mkdir -p /app/cache /app/data /app/modules /var/cache/nginx /var/log/nginx /var/lib/nginx /var/run/nginx
chown -R app:app /app/cache /app/data /app/modules /var/cache/nginx /var/log/nginx /var/lib/nginx /var/run/nginx

# Initialize database
su -s /bin/bash app -c "python3 -c 'import sys; sys.path.insert(0, \"/app\"); from app.db import db; db.init(); print(\"Database initialized.\")'"

# Start gunicorn in background
echo "Starting gunicorn..."
su -s /bin/bash app -c "cd /app && gunicorn --bind 127.0.0.1:8000 --workers 2 --threads 2 --worker-class gthread --access-logfile - --error-logfile - wsgi:app" &

# Start nginx in foreground
echo "Starting nginx..."
exec nginx -g "daemon off;"
