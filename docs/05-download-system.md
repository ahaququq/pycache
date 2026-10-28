# Download System

## Overview

The download system handles fetching files from upstream sources, caching them locally, and serving them to clients. It supports progress tracking, redirect handling, and automatic caching.

## Architecture

```
Client Request
     │
     ▼
┌─────────────────────┐
│  /cache/<path>      │  Flask route (public.serve_cached)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ sources.resolve()   │  Resolve local_path → (source_id, module, remote_url)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ cache_path(remote)  │  Check if cached
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
  Cached       Not Cached
     │             │
     ▼             ▼
  Serve from   download()
  cache
```

## Core Components

### 1. Route: `/cache/<path:local_path>` (`app/routes/public.py`)

```python
@public.route("/cache/<path:local_path>")
def serve_cached(local_path: str) -> Response:
    # 1. Resolve local_path → source_id, module, remote_url
    # 2. Check cache
    # 3. If cached: stream from cache
    # 3. If not cached: download() → cache → stream
```

**Flow**:
1. Resolve local path via `sources.resolve()`
2. Check if cached in `/app/app/cache/`
3. **If cached**: Stream directly, track serve event
4. **If not cached**: Call `download()`, cache result, stream, track events

### Key Functions

#### `serve_cached(local_path)`
- **Input**: URL-decoded local path
- **Output**: Flask Response (file stream)
- **Side effects**: Tracks serve events, updates DB

#### `download(remote_url, local_path, source_name)`
**Location**: `app/downloader.py`

Downloads from upstream with:
- Redirect following (max 10)
- Progress tracking via tracker
- Streaming to temp file → atomic move to cache
- Progress events every 500ms
- SHA256 verification

### Download Flow

```
download(remote_url)
    │
    ▼
HEAD request (probe)
    │
    ▼
GET request (stream=True)
    │
    ├─▶ 3xx Redirect → Follow (max 10)
    │
    ▼
200 OK → Stream to .part file
    │
    ▼
Progress events every 500ms
    │
    ▼
Complete → atomic rename .part → final
    │
    ▼
Tracker: download_complete
    │
    ▼
Return DownloadResult
```

### Progress Tracking

The download function emits progress events every **500ms**:

```python
# In download()
now = time.time()
if now - last_progress_time >= 0.5 and local_path:
    speed_bps = (total - last_progress_bytes) / (now - last_progress_time)
    _tracker.download_progress(local_path, total, res.content_length, speed_bps)
    last_progress_time = now
    last_progress_bytes = total
```

**Tracker Event**: `download_progress`
```json
{
  "event_type": "download_progress",
  "message": "Downloading gradle/8.5/gradle-8.5-bin.zip: 73,531,392 / 132,519,731 bytes (55.5%) @ 110.71 MB/s",
  "details": {
    "local_path": "gradle/8.5/gradle-8.5-bin.zip",
    "bytes_downloaded": 73531392,
    "total_bytes": 132519731,
    "progress_pct": 55.49,
    "speed_bps": 116089658,
    "speed_mbps": 110.71,
    "progress_pct": 55.49
  }
}
```

### DownloadResult Dataclass

```python
@dataclass
class DownloadResult:
    ok: bool = False
    status: int = 0
    final_url: str = ""
    content_type: str = ""
    content_length: Optional[int] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    error: Optional[str] = None
    cached_path: Optional[str] = None
    bytes_written: int = 0
    redirected: bool = False
```

## Probe System

### Probe Endpoint
`POST /api/probe` → checks if file exists upstream

```python
@api.route("/probe", methods=["POST"])
def probe():
    local_path = request.json.get("local_path")
    res = sources.resolve(local_path)
    result = head(remote_url)
    
    # Updates DB: exists_upstream, unavailable, unavailable_reason
    return jsonify({
        "local_path": local_path,
        "remote_url": remote_url,
        "final_url": result.final_url,
        "status": result.status,
        "exists": result.ok,
        "size": result.content_length,
        "error": result.error,
        "unavailable_reason": result.error if not result.ok else None
    })
```

### Probe Result (JSON)
```json
{
  "ok": true,
  "local_path": "gradle/8.5/gradle-8.5-bin.zip",
  "remote_url": "https://services.gradle.org/distributions/gradle-8.5-bin.zip",
  "final_url": "https://github.com/.../gradle-8.5-bin.zip",
  "status": 200,
  "exists": true,
  "size": 132519731,
  "content_type": "application/octet-stream",
  "etag": "\"0x8DBF0E62007297C\"",
  "last_modified": "Wed, 29 Nov 2023 14:18:57 GMT",
  "error": null,
  "unavailable_reason": null
}
```

### Unavailable File
```json
{
  "ok": true,
  "local_path": "gradle/1.0-milestone-2a/...",
  "status": 404,
  "exists": false,
  "size": 29,
  "error": "upstream returned 404",
  "unavailable_reason": "upstream returned 404"
}
```

## Database Updates

### On Download Complete
```sql
INSERT INTO files (source_id, local_path, remote_url, cached, cache_path, size, etag, last_modified, exists_upstream, last_checked)
VALUES (?, ?, ?, 1, ?, ?, ?, ?, 1, datetime('now'))
ON CONFLICT(source_id, local_path) DO UPDATE SET
  cached=1, cache_path=excluded.cache_path, size=excluded.size, 
  etag=excluded.etag, last_modified=excluded.last_modified,
  exists_upstream=1, last_checked=datetime('now')
```

### On Probe (Unavailable)
```sql
INSERT INTO files (source_id, local_path, remote_url, exists_upstream, unavailable, unavailable_reason, last_checked)
VALUES (?, ?, ?, 0, 1, ?, datetime('now'))
ON CONFLICT(source_id, local_path) DO UPDATE SET
  exists_upstream=0, unavailable=1, unavailable_reason=?, last_checked=datetime('now')
```

## Tracker Events

### Download Events
```python
# Start
tracker.download_start(local_path, remote_url, source_name)

# Redirect
tracker.download_redirect(local_path, from_url, to_url)

# Progress (every 500ms)
tracker.download_progress(local_path, bytes_downloaded, total_bytes, speed_bps)

# Complete
tracker.download_complete(local_path, bytes, duration_s, cache_path, source_name)

# Error
tracker.download_error(local_path, error, remote_url)
```

### Serve Events
```python
tracker.serve_start(local_path, remote_url, source_name, client_ip)
tracker.serve_complete(local_path, bytes_sent, duration_s, client_ip, from_cache)
tracker.serve_error(local_path, error, client_ip)
```

## API Endpoints

### Download File
```
POST /api/download
Content-Type: application/json
{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}
```
**Response**:
```json
{
  "ok": true,
  "bytes": 132519731,
  "cached_path": "/app/app/cache/...",
  "error": null,
  "ok": true
}
```

### Probe
```bash
curl -X POST http://localhost/api/probe \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}'
```

### Serve Cached File
```bash
# Direct download (triggers download if not cached)
curl -O http://localhost/cache/gradle/8.5/gradle-8.5-bin.zip

# Serve from cache (if cached)
curl -O http://localhost/cache/gradle/8.5/gradle-8.5-bin.zip
```

## Error Handling

| Scenario | Response |
|----------|----------|
| No source provides path | 404 "no source provides this path" |
| Upstream 404 | 502 "upstream error: upstream returned 404" |
| Redirect loop | "too many redirects" after 10 hops |
| Network error | 502 with error details |
| Disk full | 500 with "write failed" |
| Timeout | 502 with timeout error |

## Cache Management

### Eviction Policy
- **Threshold**: 90% of `CACHE_MAX_BYTES` (default 16G)
- **Target**: Free 2GB (`CACHE_EVICTION_TARGET=2G`)
- **Min free**: 512MB (`CACHE_MIN_FREE=512M`)
- **Algorithm**: LRU (least recently used)

### Purge Cache
```bash
# Via admin panel
curl -X POST http://localhost/admin/cache/purge

# Or CLI
docker compose exec pycache su -s /bin/bash app -c "rm -rf /app/app/cache/*"
```

### Manual Cache Inspection
```bash
# List cached files
ls -la /app/app/cache/

# Check DB
sqlite3 /app/app/data/cache_server.db "SELECT local_path, cached, size FROM files;"
```

## Configuration

### Environment Variables
```yaml
environment:
  CACHE_MAX_BYTES: 16G
  CACHE_EVICTION_THRESHOLD: 0.9
  CACHE_EVICTION_TARGET: 2G
  CACHE_MIN_FREE: 512M
  UPSTREAM_TIMEOUT: 120
  MAX_REDIRECTS: 10
```

### Python Config (`app/config.py`)
```python
CACHE_MAX_BYTES = _env_bytes("CACHE_MAX_BYTES", 16 * 1024**3)
CACHE_EVICTION_THRESHOLD = float(os.environ.get("CACHE_EVICTION_THRESHOLD", "0.9"))
CACHE_EVICTION_TARGET = _env_bytes("CACHE_EVICTION_TARGET", 2 * 1024**3)
CACHE_MIN_FREE = _env_bytes("CACHE_MIN_FREE", 512 * 1024**2)
UPSTREAM_TIMEOUT = _env_int("UPSTREAM_TIMEOUT", 120)
MAX_REDIRECTS = _env_int("MAX_REDIRECTS", 10)
```

## Testing Downloads

```bash
# Valid file (cached)
curl -X POST http://localhost/api/download \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}'

# Probe unavailable file
curl -X POST http://localhost/api/probe \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/1.0-milestone-2a/gradle-1.0-milestone-2a-bin.zip"}'

# Serve cached file
curl -O http://localhost/cache/gradle/8.5/gradle-8.5-bin.zip

# Probe unavailable
curl -X POST http://localhost/api/probe \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/1.0-milestone-2a/gradle-1.0-milestone-2a-bin.zip"}'
```

## Monitoring Downloads

### Live Tracker
```bash
# Web UI
open http://localhost/admin/tracker

# SSE stream
curl -N http://localhost/api/tracker/stream

# Events API
curl http://localhost/api/tracker/events?limit=10
curl http://localhost/api/tracker/stats
```

### Logs
```bash
docker compose logs -f pycache | grep -i download
```

## Troubleshooting Downloads

| Symptom | Cause | Fix |
|---------|-------|-----|
| 502 upstream error | Upstream unreachable | Check DNS, network |
| 502 timeout | Slow upstream | Increase `UPSTREAM_TIMEOUT` |
| 502 redirect loop | Redirect loop | Check upstream, reduce `MAX_REDIRECTS` |
| Slow downloads | Slow upstream | Check network, increase timeout |
| Cache full | Disk full | Purge cache, increase `CACHE_MAX_BYTES` |
| 404 not found | Not in any source | Add source or mapping |