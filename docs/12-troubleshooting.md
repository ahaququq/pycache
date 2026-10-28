# Troubleshooting

## Common Issues

### Application Won't Start

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container exits immediately | Build failed | Check `docker compose logs pycache` |
| Port 80 in use | Another service on port 80 | Stop conflicting service or change port |
| Permission denied | Volume permissions | Run `docker compose exec pycache chown -R app:app /app/app/cache /app/app/data` |

### Container Health

```bash
# Check container status
docker compose ps

# Check logs
docker compose logs -f pycache

# Check health
curl http://localhost/health
```

### Container Restarting

```bash
# Check exit code
docker compose ps

# View logs
docker compose logs pycache --tail=100

# Common causes:
# - OOM (out of memory) → Increase container memory
# - Port conflict → Check port 80/8000
# - Config error → Check environment variables
```

## Download Issues

### Download Fails

| Symptom | Cause | Fix |
|---------|-------|-----|
| `{"ok":false,"error":"no source provides this path"}` | File not in any source | Add source or check path |
| `{"ok":false,"error":"upstream returned 404"}` | File not on upstream | Verify file exists upstream |
| `{"ok":false,"error":"upstream returned 403"}` | Upstream blocks access | Check upstream auth/headers |
| `{"ok":false,"error":"upstream returned 502"}` | Upstream error | Retry, check upstream status |

### Slow Downloads

| Cause | Fix |
|-------|-----|
| Slow upstream | Increase `UPSTREAM_TIMEOUT` (default 120s) |
| Network issues | Check container network, DNS |
| Slow disk | Check disk I/O, use SSD |

### Download Stuck

```bash
# Check active downloads
curl http://localhost/api/tracker/events?type=download_progress

# Check disk space
df -h /app/app/cache

# Check process
docker compose exec pycache ps aux | grep python
```

### Cache Issues

| Problem | Fix |
|---------|-----|
| Cache full | `curl -X POST http://localhost/admin/cache/purge` |
| Corrupted file | Delete file from `/app/app/cache/` and DB |
| Permission error | `docker compose exec pycache chown -R app:app /app/app/cache` |

### File Not Found (404)

| Scenario | Fix |
|----------|-----|
| File in source but 404 | Run probe: `POST /api/probe` |
| File cached but 404 | Check `/app/app/cache/` permissions |
| Source not loaded | Check `/admin/modules` for module status |

## Network Issues

### DNS Problems

```bash
# Test DNS from container
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import socket
print(socket.getaddrinfo(\"services.gradle.org\", 443))
'
"

# Test DoH
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sys; sys.path.insert(0, \"/app\")
from app.doh import get_doh_session
s = get_doh_session()
print(s.resolver.resolve(\"services.gradle.org\"))
'
"
```

### DNS Configuration

```yaml
# docker-compose.yml
services:
  pycache:
    dns:
      - 1.1.1.1
      - 8.8.8.8
```

### DoH Issues

```bash
# Test DoH endpoints
curl -H "Accept: application/dns-json" "https://cloudflare-dns.com/dns-query?name=services.gradle.org&type=A"
curl -H "Accept: application/dns-json" "https://dns.google/dns-query?name=services.gradle.org&type=A"

# Fallback to system DNS if DoH fails
# Check container DNS
docker compose exec pycache cat /etc/resolv.conf
```

## Database Issues

### Database Locked

```bash
# Check for locks
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sqlite3
conn = sqlite3.connect(\"/app/app/data/cache_server.db\", timeout=10)
print(conn.execute(\"SELECT * FROM files LIMIT 1;\").fetchone())
'
"
```

### Database Corruption

```bash
# Backup first
docker compose exec pycache sqlite3 /app/app/data/cache_server.db .backup /app/app/data/backup.db

# Check integrity
docker compose exec pycache sqlite3 /app/app/data/cache_server.db "PRAGMA integrity_check;"

# Rebuild if needed
docker compose exec pycache sqlite3 /app/app/data/cache_server.db ".recover" | sqlite3 /app/app/data/new.db
```

### Database Locked Error

```bash
# Kill processes holding lock
docker compose exec pycache fuser /app/app/data/cache_server.db

# Or restart
docker compose restart pycache
```

## Cache Issues

### Cache Full

```bash
# Check usage
docker compose exec pycache df -h /app/app/cache

# Purge cache
curl -X POST http://localhost/admin/cache/purge \
  -H "Cookie: cache_admin=..." \
  -H "Content-Type: application/x-www-form-urlencoded"

# Or CLI
docker compose exec pycache su -s /bin/bash app -c "rm -rf /app/app/cache/*"
```

### Eviction Not Working

```bash
# Check settings
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sys; sys.path.insert(0, \"/app\")
from app.config import CACHE_MAX_BYTES, CACHE_EVICTION_THRESHOLD
print(f\"Max: {CACHE_MAX_BYTES}, Threshold: {CACHE_EVICTION_THRESHOLD}\")
'
"

# Check disk space
df -h /app/app/cache
```

### Eviction Not Triggering

```bash
# Check threshold
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sys; sys.path.insert(0, \"/app\")
from app.cache import stats
s = stats()
print(f\"Used: {s.total_bytes}, Max: {s.max_bytes}, Pct: {s.total_bytes/s.max_bytes*100:.1f}%\")
'
"
```

## Module Issues

### Module Not Loading

```bash
# Check module status
curl -b /tmp/cookies.txt http://localhost/admin/modules

# Check logs
docker compose logs pycache | grep -i module

# Reload modules
curl -b /tmp/cookies.txt -X POST http://localhost/api/modules/reload
```

### Module Not Found

```bash
# Check module directory
docker compose exec pycache ls -la /app/app/modules/

# Check module code
cat /home/ahaququq/Dokumenty/Yapping/PyCache/app/modules/gradle.py
```

### Module Reload Issues

```bash
# Force reload
curl -b /tmp/cookies.txt -X POST http://localhost/api/modules/reload

# Check watchdog
docker compose logs pycache | grep -i watchdog
```

## Module Development

### Adding New Module

1. Create `/app/modules/mymodule.py`
2. Implement `ModuleBase` interface
3. Register in `app/modules/__init__.py` (auto-loaded)

### Module Interface

```python
class ModuleBase:
    name = "mymodule"
    display_name = "My Module"
    
    def list_items(self) -> list[Item]:
        """Return list of Item objects"""
        pass
    
    def resolve(self, local_path: str) -> Optional[str]:
        """Return remote URL for local path"""
        pass
```

### Module Debugging

```bash
# Test module directly
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sys; sys.path.insert(0, \"/app\")
from app.modules.gradle import GradleModule
m = GradleModule()
items = m.list_items()
print(f\"Found {len(items)} items\")
print(items[0].local_path if items else \"None\")
'
"
```

## Admin Panel Issues

### Cannot Login

```bash
# Check cookie
curl -v http://localhost/admin/login

# Check cookie in browser dev tools
# Name: cache_admin
# Domain: localhost
# Path: /
```

### First Time Setup

```bash
# Access setup page
curl http://localhost/admin/setup

# Create admin
curl -X POST http://localhost/admin/setup \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=secret&password2=secret"
```

### Permission Denied

```bash
# Check if admin user exists
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import sqlite3
conn = sqlite3.connect(\"/app/app/data/cache_server.db\")
print(conn.execute(\"SELECT * FROM admin_users\").fetchall())
'
"
```

## Logs

### View Logs

```bash
# All logs
docker compose logs -f pycache

# Filter errors
docker compose logs pycache 2>&1 | grep -i error

# Last 100 lines
docker compose logs --tail=100 pycache
```

### Log Levels

```yaml
environment:
  LOG_LEVEL: DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### Log Rotation

```bash
# Check logrotate config
docker compose exec pycache cat /etc/logrotate.d/nginx

# Rotate manually
docker compose exec pycache logrotate -f /etc/logrotate.d/nginx
```

## Performance Issues

### Slow Responses

```bash
# Check response time
curl -w "@curl-format.txt" -o /dev/null -s http://localhost/health

# Check gunicorn workers
docker compose exec pycache ps aux | grep gunicorn

# Increase workers
# In docker-entrypoint.sh or wsgi.py
gunicorn --workers 4 --threads 2 ...
```

### Memory Issues

```bash
# Check memory
docker stats pycache

# Limit memory
# docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2G
```

### Disk Space

```bash
# Check disk
df -h /app/app/cache
df -h /app/app/data

# Clean up
docker system prune -f
docker compose exec pycache su -s /bin/bash app -c "rm -rf /app/app/cache/*"
```

## Debug Mode

```yaml
environment:
  DEBUG: "true"
  LOG_LEVEL: DEBUG
```

```bash
# Enable debug in running container
docker compose exec pycache su -s /bin/bash app -c "
python3 -c '
import logging
logging.getLogger().setLevel(logging.DEBUG)
'
"
```

## Debug Endpoints

### Debug Download
```bash
# Test download
curl -X POST http://localhost/api/download \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}'
```

### Debug Probe
```bash
curl -X POST http://localhost/api/probe \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}'
```

### Debug Tracker
```bash
# SSE stream
curl -N http://localhost/api/tracker/stream

# Events
curl http://localhost/api/tracker/events?limit=5

# Stats
curl http://localhost/api/tracker/stats
```

## Health Checks

### Liveness
```bash
curl http://localhost/health
```

### Readiness
```bash
curl http://localhost/api/tracker/stats
```

### Dependency Checks

```bash
# Database
docker compose exec pycache sqlite3 /app/app/data/cache_server.db "SELECT 1;"

# DNS
docker compose exec pycache dig @1.1.1.1 services.gradle.org

# Upstream
curl -I https://services.gradle.org/distributions/gradle-8.5-bin.zip
```

## Emergency Procedures

### Complete Reset

```bash
# WARNING: Data loss!
docker compose down -v
docker compose up -d --build
```

### Partial Reset (Keep Cache)

```bash
docker compose down
docker compose up -d --build
```

### Database Only Reset

```bash
docker compose exec pycache su -s /bin/bash app -c "
sqlite3 /app/app/data/cache_server.db 'DELETE FROM files; DELETE FROM log_entries;'
"
```

## Useful One-Liners

```bash
# Watch downloads in real-time
watch -n 1 'curl -s http://localhost/api/tracker/stats | jq'

# Monitor cache size
watch -n 5 'docker compose exec pycache du -sh /app/app/cache'

# Monitor events
curl -N http://localhost/api/tracker/stream

# Check unavailable files
curl -s http://localhost/api/tracker/events?type=download_error | jq

# Check cache hit ratio
curl -s http://localhost/api/tracker/stats | jq '.download_complete / (.download_complete + .download_error)'
```