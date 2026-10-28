# Appendix

## File Structure

```
/home/ahaququq/Dokumenty/Yapping/PyCache/
├── app/
│   ├── __init__.py              # Flask app factory, CSP, blueprints
│   ├── auth.py                  # Authentication, CSRF, cookies
│   ├── cache.py                 # Cache operations (store, evict, stats)
│   ├── config.py                # Configuration management
│   ├── db.py                    # SQLite database layer
│   ├── doh.py                   # DNS over HTTPS resolver
│   ├── downloader.py            # Streaming downloader with progress
│   ├── log_handler.py           # DB logging handler
│   ├── tracker.py               # Live event tracker (SSE)
│   ├── cache.py                 # Cache operations (alias for cache.py)
│   ├── modules/
│   │   ├── __init__.py          # Module registry/loader
│   │   ├── base.py              # ModuleBase abstract class
│   │   ├── gradle.py            # Gradle distributions module
│   │   └── db.py                # DB-backed source module
│   ├── routes/
│   │   ├── __init__.py          # Blueprint registration
│   │   ├── public.py            # Public routes (cache, info, probe)
│   │   ├── admin.py             # Admin panel routes
│   │   └── api.py               # JSON API endpoints
│   ├── static/
│   │   ├── css/
│   │   │   └── main.css
│   │   └── js/
│   │       └── main.js
│   └── templates/
│       ├── admin/
│       │   ├── base.html
│       │   ├── dashboard.html
│       │   ├── login.html
│       │   ├── tracker.html
│       │   ├── logs.html
│       │   ├── cache.html
│       │   ├── modules.html
│       │   ├── module_edit.html
│       │   ├── modules.html
│       │   ├── sources.html
│       │   └── ...
│       ├── admin/
│       ├── base.html
│       ├── index.html
│       ├── by_path.html
│       ├── by_source.html
│       └── by_source_detail.html
├── nginx/
│   ├── nginx.conf
│   └── conf.d/
│       └── cache.conf
├── test-gradle-project/
│   ├── gradle/
│   │   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── docs/
│   ├── 00-overview.md
│   ├── 01-installation.md
│   ├── 02-running.md
│   ├── 03-admin-panel.md
│   ├── 04-live-tracker.md
│   ├── 05-download-system.md
│   ├── 06-doh-dns.md
│   ├── 07-unavailable-files.md
│   ├── 08-log-viewer.md
│   ├── 09-gradle-integration.md
│   ├── 10-configuration.md
│   ├── 11-api-reference.md
│   ├── 12-troubleshooting.md
│   └── 13-appendix.md
├── check_db.py
├── check_db2.py
├── check_db3.py
├── docker-compose.yml
├── docker-entrypoint.sh
├── Dockerfile
├── requirements.txt
├── wsgi.py
└── README.md
```

## Key Files Reference

### Application Entry Points

| File | Purpose |
|------|---------|
| `wsgi.py` | Gunicorn entry point |
| `docker-entrypoint.sh` | Container startup script |
| `app/__init__.py` | Flask app factory |

### Core Modules

| File | Purpose |
|------|---------|
| `app/__init__.py` | Flask app factory, CSP, blueprints |
| `app/config.py` | Configuration from environment |
| `app/db.py` | SQLite database layer |
| `app/downloader.py` | Streaming downloads with progress |
| `app/tracker.py` | SSE event streaming |
| `app/sources.py` | Source manager |
| `app/doh.py` | DoH DNS resolver |
| `app/cache.py` | Cache operations |

### Route Modules

| File | Prefix | Purpose |
|------|--------|---------|
| `app/routes/public.py` | `/` | Public pages, cache proxy |
| `app/routes/admin.py` | `/admin` | Admin panel |
| `app/routes/api.py` | `/api` | JSON API endpoints |

### Modules

| File | Kind | Description |
|------|------|-------------|
| `app/modules/gradle.py` | `gradle` | Gradle distributions |
| `app/modules/db.py` | `db` | DB-backed mappings |

### Templates

| Template | Purpose |
|----------|---------|
| `base.html` | Base layout with CSP |
| `index.html` | Home page |
| `by_path.html` | Browse by path |
| `by_source.html` | Browse by source |
| `by_source_detail.html` | Source detail view |
| `admin/tracker.html` | Live tracker dashboard |
| `admin/logs.html` | Log viewer |
| `admin/modules.html` | Module list |
| `admin/module_edit.html` | Monaco editor |

### Static Assets

| File | Purpose |
|------|---------|
| `static/css/main.css` | All styles |
| `static/js/main.js` | Tracker, notifications, probe modal |

## Database Schema

### Sources
```sql
CREATE TABLE sources (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    kind TEXT,           -- 'gradle', 'db'
    config TEXT,         -- JSON
    enabled INTEGER,
    created_at TEXT,
    updated_at TEXT
);
```

### Files
```sql
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    local_path TEXT,
    remote_url TEXT,
    size INTEGER,
    cached INTEGER DEFAULT 0,
    cache_path TEXT,
    etag TEXT,
    last_modified TEXT,
    exists_upstream INTEGER DEFAULT 0,
    unavailable INTEGER DEFAULT 0,
    unavailable_reason TEXT,
    last_checked TEXT,
    UNIQUE(source_id, local_path)
);
```

### Mappings (DB sources)
```sql
CREATE TABLE mappings (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    local_path TEXT,
    remote_url TEXT,
    enabled INTEGER DEFAULT 1,
    UNIQUE(source_id, local_path)
);
```

### Admin Users
```sql
CREATE TABLE admin_users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    pw_hash TEXT,
    pw_salt TEXT,
    created TEXT DEFAULT (datetime('now'))
);
```

### Log Entries
```sql
CREATE TABLE log_entries (
    id INTEGER PRIMARY KEY,
    timestamp TEXT DEFAULT (datetime('now')),
    level TEXT,
    module TEXT,
    message TEXT,
    details TEXT
);
```

### Meta
```sql
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

## Key Algorithms

### Cache Eviction (LRU)
```python
# In cache.py
def ensure_space(estimated_bytes: int) -> None:
    stats = get_stats()
    if stats.total_bytes + estimated_bytes > CACHE_MAX_BYTES * CACHE_EVICTION_THRESHOLD:
        target = CACHE_MAX_BYTES - CACHE_EVICTION_TARGET
        # LRU eviction
        rows = db.fetchall(
            "SELECT cache_path FROM files WHERE cached=1 ORDER BY last_checked ASC"
        )
        for row in rows:
            if stats.total_bytes <= target:
                break
            path = Path(row["cache_path"])
            if path.exists():
                path.unlink()
                db.execute("UPDATE files SET cached=0, cache_path=NULL WHERE cache_path=?", (str(path),))
                stats.total_bytes -= path.stat().st_size
```

### Download with Progress
```python
def download(url: str, local_path: str = "", source_name: str = "") -> DownloadResult:
    # 1. HEAD request to get size
    # 2. GET stream=True
    # 3. Write to .part file
    # 4. Progress every 500ms → tracker.download_progress()
    # 5. Atomic rename .part → final
    # 6. Tracker: download_complete
```

### DoH Resolution
```python
def resolve(hostname: str) -> list[str]:
    for endpoint in [cloudflare, google]:
        resp = session.get(endpoint, params={"name": hostname, "type": "A"})
        data = resp.json()
        if data["Status"] == 0:
            return [a["data"] for a in data["Answer"] if a["type"] == 1]
    return system_resolve(hostname)
```

### SSE Event Format
```python
event = TrackerEvent(
    id=42,
    timestamp="2026-10-27T15:45:27",
    event_type="download_progress",
    message="Downloading... 55.5% @ 110 MB/s",
    details={"progress_pct": 55.5, "speed_mbps": 110}
)
# SSE format:
# data: {"id":42,"timestamp":"...","event_type":"download_progress",...}
# 
```

### CSP Nonce Generation
```python
@app.before_request
def generate_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)

@app.after_request
def add_csp_header(response):
    nonce = getattr(g, 'csp_nonce', '')
    csp = f"script-src 'self' 'unsafe-eval' 'nonce-{nonce}' https://cdn.jsdelivr.net blob:;"
    response.headers['Content-Security-Policy'] = csp
    return response
```

## Environment Variables Summary

```bash
# Cache
CACHE_MAX_BYTES=16G
CACHE_EVICTION_THRESHOLD=0.9
CACHE_EVICTION_TARGET=2G
CACHE_MIN_FREE=512M

# Network
UPSTREAM_TIMEOUT=120
MAX_REDIRECTS=10
UPSTREAM_USER_AGENT=pycache/1.0

# DNS
DNS_1=1.1.1.1
DNS_2=8.8.8.8

# Server
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=INFO

# Admin
ADMIN_COOKIE_MAX_AGE=604800
CSRF_TOKEN_LENGTH=32

# Modules
MODULE_MAX_RELOAD_FAILURES=3
MODULE_RELOAD_INTERVAL=5
MODULES_DIR=/app/app/modules

# Debug
DEBUG=false
LOG_LEVEL=INFO
```

## Ports

| Port | Service | Access |
|------|---------|--------|
| 80 | Nginx | External |
| 8000 | Flask | Internal |

## Volumes

| Volume | Mount | Purpose |
|--------|-------|---------|
| `cache-data` | `/app/app/cache` | Cached files |
| `app-data` | `/app/app/data` | SQLite DB |

## Health Check

```bash
curl http://localhost/health
# {"status":"ok","cache_max_bytes":17179869184}
```

## Backup/Restore

```bash
# Backup
docker compose exec pycache sqlite3 /app/app/data/cache_server.db .dump > backup.sql

# Restore
docker compose exec -T pycache sqlite3 /app/app/data/cache_server.db < backup.sql
```

## Monitoring Commands

```bash
# Live tracker
curl -N http://localhost/api/tracker/stream

# Stats
curl http://localhost/api/tracker/stats

# Events
curl http://localhost/api/tracker/events?limit=10

# Download test
curl -X POST http://localhost/api/download \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}'

# Probe
curl -X POST http://localhost/api/probe \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}'

# Cache stats
docker compose exec pycache du -sh /app/app/cache

# DB stats
docker compose exec pycache sqlite3 /app/app/data/cache_server.db \
  "SELECT COUNT(*), SUM(size) FROM files WHERE cached=1;"
```

## Support

- **Logs**: `docker compose logs -f pycache`
- **Shell**: `docker compose exec pycache bash`
- **Database**: `docker compose exec pycache sqlite3 /app/app/data/cache_server.db`
- **Restart**: `docker compose restart pycache`
- **Rebuild**: `docker compose down && docker compose up -d --build`