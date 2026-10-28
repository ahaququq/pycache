# Running the Application

## Starting the Application

```bash
cd /home/ahaququq/Dokumenty/Yapping/PyCache
docker compose up -d --build
```

The `--build` flag ensures the latest code is built. The `-d` flag runs in detached mode.

## Accessing the Application

| URL | Description |
|-------|-------------|
| `http://localhost/` | Main info page |
| `http://localhost/admin/` | Admin panel (login required) |
| `http://localhost/admin/tracker` | Live tracker dashboard |
| `http://localhost/admin/logs` | Event log viewer |
| `http://localhost/health` | Health check endpoint |

## Health Check

```bash
curl http://localhost/health
# {"status":"ok","cache_max_bytes":17179869184}
```

## Viewing Logs

```bash
# Live logs
docker compose logs -f pycache

# Last 100 lines
docker compose logs --tail=100 pycache

# Filter by level
docker compose logs pycache 2>&1 | grep -i error
```

## Admin Panel Access

1. **Main app**: `http://localhost/`
2. **Admin**: `http://localhost/admin/`
3. **Login**: First time → `/admin/setup` to create account
4. **Default credentials**: `ahaququq` / `testpass` (if already set)

## Common Commands

| Command | Description |
|---------|-------------|
| `docker compose up -d --build` | Build and start in background |
| `docker compose down` | Stop and remove containers |
| `docker compose down -v` | Stop and remove volumes (data loss!) |
| `docker compose restart pycache` | Restart service |
| `docker compose logs -f` | Follow logs |
| `docker compose exec pycache bash` | Shell into container |

## Health Checks

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Basic health check |
| `GET /api/tracker/stats` | Tracker statistics |
| `GET /api/tracker/events` | Recent events (JSON) |

## Common Operations

### Restart Services
```bash
docker compose restart pycache
```

### Rebuild and Restart
```bash
docker compose down && docker compose up -d --build
```

### Clear Cache
```bash
docker compose exec pycache su -s /bin/bash app -c "rm -rf /app/app/cache/*"
```

### View Database
```bash
docker compose exec pycache sqlite3 /app/app/data/cache_server.db ".tables"
docker compose exec pycache sqlite3 /app/app/data/cache_server.db "SELECT * FROM files LIMIT 5;"
```

## Monitoring

### Real-time Tracker
```bash
# Web UI
open http://localhost/admin/tracker

# SSE stream (for debugging)
curl -N http://localhost/api/tracker/stream
```

### Logs
```bash
# Application logs
docker compose logs -f pycache

# Nginx access logs
docker compose exec pycache tail -f /var/log/nginx/access.log

# Nginx error logs
docker compose exec pycache tail -f /var/log/nginx/error.log
```

## Backup & Restore

### Backup Database
```bash
docker compose exec pycache sqlite3 /app/app/data/cache_server.db .dump > backup.sql
```

### Restore Database
```bash
docker compose exec -T pycache sqlite3 /app/app/data/cache_server.db < backup.sql
```

### Backup Cache Files
```bash
docker run --rm -v pycache_cache-data:/data -v $(pwd):/backup alpine tar czf /backup/cache-backup.tar.gz -C /data .
```

## Scaling Considerations

| Resource | Recommendation |
|----------|----------------|
| **Cache size** | Set `CACHE_MAX_BYTES` in docker-compose.yml |
| **Eviction** | Triggers at 90% (`CACHE_EVICTION_THRESHOLD=0.9`) |
| **Eviction target** | Frees 2GB by default (`CACHE_EVICTION_TARGET=2G`) |
| **Min free space** | 512MB (`CACHE_MIN_FREE=512M`) |

## Network Configuration

### DoH DNS
Configured in `docker-compose.yml`:
```yaml
dns:
  - 1.1.1.1   # Cloudflare
  - 8.8.8.8   # Google
```

### Ports
| Port | Service | Access |
|--------|---------|--------|
| 80 | Nginx (HTTP) | External |
| 8000 | Flask (internal) | Internal only |

## Log Rotation

Nginx logs are managed by logrotate inside the container:
```bash
docker compose exec pycache cat /etc/logrotate.d/nginx
```

## Performance Tuning

### Cache Settings (docker-compose.yml)
```yaml
environment:
  CACHE_MAX_BYTES: 16G
  CACHE_EVICTION_THRESHOLD: 0.9
  CACHE_EVICTION_TARGET: 2G
  CACHE_MIN_FREE: 512M
  UPSTREAM_TIMEOUT: 120
  MAX_REDIRECTS: 10
```

### Gunicorn Workers
```bash
# In docker-entrypoint.sh or wsgi.py
gunicorn --workers 4 --threads 2 ...
```

## Upgrading

```bash
cd /home/ahaququq/Dokumenty/Yapping/PyCache
git pull
docker compose down
docker compose up -d --build
```

## Uninstalling

```bash
# Stop and remove containers
docker compose down

# Remove volumes (DATA LOSS!)
docker compose down -v

# Remove images
docker rmi pycache-pycache
```