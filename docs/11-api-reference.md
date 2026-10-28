# API Reference

## Base URL

```
http://localhost:80
```

All endpoints are prefixed with `/` or `/api/`.

## Authentication

- **Admin endpoints**: Require `cache_admin` cookie
- **Public endpoints**: No authentication
- **First-time setup**: `/admin/setup` (localhost only)

## Public Endpoints

### Health Check
```
GET /health
```
**Response:**
```json
{
  "status": "ok",
  "cache_max_bytes": 17179869184
}
```

### Root Redirect
```
GET /
```
Redirects to `/info`.

### Info Index
```
GET /info
```
**Response**: HTML page with total upstream count.

### By Path
```
GET /info/by-path?q=<filter>
```
**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Filter paths |

**Response**: HTML page with file table.

### By Source
```
GET /info/by-source
```
**Response**: HTML page with source list.

### By Source Detail
```
GET /info/by-source/<source_id>
```
**Response**: HTML page with files for that source.

### Cache Proxy
```
GET /cache/<path:local_path>
```
Streams file from cache or downloads from upstream.

**Response**: File stream (application/octet-stream)

### Probe (GET)
```
GET /probe/<path:local_path>
```
Checks upstream existence.

**Response:**
```json
{
  "local_path": "gradle/8.5/gradle-8.5-bin.zip",
  "remote_url": "https://services.gradle.org/distributions/gradle-8.5-bin.zip",
  "final_url": "https://...",
  "status": 200,
  "exists": true,
  "size": 132519731,
  "content_type": "application/octet-stream",
  "etag": "\"0x8DBF0E62007297C\"",
  "last_modified": "Wed, 29 Nov 2023 14:18:57 GMT",
  "error": null
}
```

## Admin Endpoints

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/setup` | GET/POST | First-time admin setup |
| `/admin/login` | GET/POST | Login |
| `/admin/logout` | GET | Logout |

### Dashboard
```
GET /admin/
```
Admin dashboard with stats and quick actions.

### Live Tracker
```
GET /admin/tracker
```
Real-time dashboard with progress bars and event log.

### Log Viewer
```
GET /admin/logs?page=1&level=ERROR&module=download
```
Query params:
- `page`: Page number (default 1)
- `level`: Filter by level
- `module`: Filter by module

```
POST /admin/logs/clear
```
Clears all log entries.

### Cache Management
```
GET /admin/cache
POST /admin/cache/purge
GET /admin/cache/config
```

### Sources
```
GET /admin/sources
GET /admin/sources/new
POST /admin/sources/new
GET /admin/sources/<id>/edit
POST /admin/sources/<id>/edit
POST /admin/sources/<id>/delete
```

### Source Mappings (DB sources)
```
GET /admin/sources/<id>/mappings
GET /admin/sources/<id>/mappings/new
POST /admin/sources/<id>/mappings/new
POST /admin/sources/<id>/mappings/<mapping_id>/delete
```

### Modules
```
GET /admin/modules
GET /admin/modules/new
POST /admin/modules/new
GET /admin/modules/<name>
GET /admin/modules/<name>/edit
POST /admin/modules/<name>/edit
POST /admin/modules/<name>/reload
```

## API Endpoints

### Probe
```
POST /api/probe
Content-Type: application/json
{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}
```
**Response:**
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

### Download
```
POST /api/download
Content-Type: application/json
{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}
```
**Response:**
```json
{
  "ok": true,
  "bytes": 132519731,
  "cached_path": "/app/app/cache/...",
  "error": null
}
```

### Sources Reload
```
POST /api/sources/reload
```
**Response:** `{"ok": true}`

### Modules Reload
```
POST /api/modules/reload
```
**Response:** `{"ok": true}`

## Tracker API

### SSE Stream
```
GET /api/tracker/stream
```
**Format**: Server-Sent Events
```
data: {"id":1,"timestamp":"2026-10-27T15:45:27","event_type":"download_start","message":"Starting download: gradle/8.5/gradle-8.5-bin.zip","details":{"local_path":"gradle/8.5/gradle-8.5-bin.zip","remote_url":"https://...","source_name":"gradle_dist"}}

data: {"id":2,"timestamp":"2026-10-27T15:45:28","event_type":"download_progress","message":"Downloading...","details":{"bytes_downloaded":65536,"total_bytes":132519731,"progress_pct":0.05,"speed_bps":81889}}

: heartbeat

data: {"id":3,"timestamp":"2026-10-27T15:45:29","event_type":"download_complete","message":"Downloaded...","details":{...}}
```

### Events List
```
GET /api/tracker/events?limit=100&type=download_complete
```
**Query params:**
- `limit`: Max events (default 100)
- `type`: Comma-separated event types

**Response:**
```json
[
  {
    "id": 1,
    "timestamp": "2026-10-27T15:45:27",
    "event_type": "download_start",
    "message": "Starting download: gradle/8.5/gradle-8.5-bin.zip",
    "details": {"local_path": "gradle/8.5/gradle-8.5-bin.zip", "remote_url": "https://...", "source_name": "gradle_dist"}
  }
]
```

### Statistics
```
GET /api/tracker/stats
```
```json
{
  "download_start": 10,
  "download_progress": 5,
  "download_complete": 8,
  "download_error": 0,
  "serve_start": 5,
  "serve_complete": 4,
  "serve_error": 0,
  "probe_start": 3,
  "probe_complete": 3
}
```

### Clear Events (Not implemented)
```
POST /api/tracker/clear
```

## Error Responses

### Standard Error Format
```json
{
  "ok": false,
  "error": "Error description"
}
```

### HTTP Status Codes
| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 500 | Internal Server Error |
| 502 | Bad Gateway (upstream error) |

### Common Errors

| Endpoint | Error | HTTP | Fix |
|----------|-------|------|-----|
| `/api/download` | "no source provides this path" | 404 | Add source or check path |
| `/api/download` | "upstream returned 404" | 502 | File not available upstream |
| `/api/download` | "upstream error: ..." | 502 | Check upstream connectivity |
| `/api/probe` | "no source provides this path" | 404 | Check source configuration |
| `/cache/<path>` | "no source provides this path" | 404 | Add source or check path |

## Rate Limits

No explicit rate limiting implemented. Consider adding for production.

## CORS

Not configured (same-origin only). Add CORS headers if needed.

## WebSocket

Not implemented. Uses SSE for real-time updates.

## Versioning

No API versioning. Breaking changes require coordination.

## OpenAPI/Swagger

Not implemented. Consider adding for production.

## Example Clients

### cURL
```bash
# Probe
curl -X POST http://localhost/api/probe \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}'

# Download
curl -X POST http://localhost/api/download \
  -H "Content-Type: application/json" \
  -d '{"local_path": "gradle/8.5/gradle-8.5-bin.zip"}'

# Tracker events
curl http://localhost/api/tracker/events?limit=10
```

### Python
```python
import requests

# Probe
r = requests.post("http://localhost/api/probe", 
    json={"local_path": "gradle/8.5/gradle-8.5-bin.zip"})
print(r.json())

# Download
r = requests.post("http://localhost/api/download",
    json={"local_path": "gradle/8.5/gradle-8.5-bin.zip"})
print(r.json())

# SSE stream
import sseclient
resp = requests.get("http://localhost/api/tracker/stream", stream=True)
client = sseclient.SSEClient(resp)
for event in client.events():
    print(json.loads(event.data))
```

### JavaScript
```javascript
// Probe
const resp = await fetch('/api/probe', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({local_path: 'gradle/8.5/gradle-8.5-bin.zip'})
});
const data = await resp.json();

// SSE stream
const es = new EventSource('/api/tracker/stream');
es.onmessage = (e) => {
  const event = JSON.parse(e.data);
  console.log(event.event_type, event.message);
};
```