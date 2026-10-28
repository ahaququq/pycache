# Log Viewer

## Overview

The Log Viewer provides a web-based interface to browse and filter application logs stored in the SQLite database.

## Access

**URL**: `http://localhost:80/admin/logs`

## Features

### Filtering
| Filter | Values |
|--------|--------|
| **Level** | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| **Module** | download, tracker, cache, sources, routes, auth, etc. |
| **Search** | Text search in message and details |

### Pagination
- **100 entries per page**
- Previous/Next navigation
- Total count displayed

### Event Details
- Click any event row → Modal with full JSON details
- Shows all fields including `details` JSON

### Clear Logs
- **Button**: "Clear Logs" (POST `/admin/logs/clear`)
- Requires confirmation
- Deletes all entries from `log_entries` table

## Database Schema

```sql
CREATE TABLE log_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    level       TEXT NOT NULL,  -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    module      TEXT NOT NULL,  -- download, tracker, cache, sources, etc.
    message     TEXT NOT NULL,
    details     TEXT            -- optional JSON with extra context
);

CREATE INDEX idx_log_timestamp ON log_entries(timestamp);
CREATE INDEX idx_log_level ON log_entries(level);
CREATE INDEX idx_log_module ON log_entries(module);
```

## Log Handler Implementation

### `app/log_handler.py`

```python
class DBLogHandler(logging.Handler):
    """Logging handler that stores log records in the database."""
    
    def __init__(self, level: int = logging.WARNING) -> None:
        super().__init__(level)
    
    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Extract module name
            module = record.name
            if module.startswith("app."):
                module = module[4:]
            elif module.startswith("routes."):
                module = module[7:]
            
            # Extract extra details
            details = {}
            for key, value in record.__dict__.items():
                if key not in ('name', 'msg', 'args', 'levelname', ...):
                    details[key] = value
            
            message = self.format(record) if self.formatter else record.getMessage()
            
            db.execute(
                "INSERT INTO log_entries (level, module, message, details) VALUES (?, ?, ?, ?)",
                (record.levelname, module, message, json.dumps(details) if details else None)
            )
            db._conn().commit()
        except Exception:
            self.handleError(record)
```

### Registration in `app/__init__.py`

```python
from .log_handler import DBLogHandler

db_handler = DBLogHandler()
db_handler.setLevel(logging.INFO)  # Log INFO and above
db_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logging.getLogger().addHandler(db_handler)
app.logger.addHandler(db_handler)
```

## Log Levels

| Level | Color | Use Case |
|-------|-------|----------|
| DEBUG | Gray | Detailed debug info |
| INFO | Blue | General operations |
| WARNING | Yellow | Recoverable issues |
| ERROR | Red | Errors, failed operations |
| CRITICAL | Red + Bold | System failures |

## Event Types Logged

| Module | Events |
|--------|--------|
| **download** | start, redirect, progress, complete, error |
| **tracker** | SSE connections, event processing |
| **cache** | eviction, purge, space checks |
| **sources** | reload, listing failures |
| **routes** | serve, probe, download |
| **download** | progress, complete, error |
| **auth** | login, logout, setup |

## Example Log Entries

```json
{
  "id": 42,
  "timestamp": "2026-10-27 15:45:27",
  "level": "INFO",
  "module": "download",
  "message": "Downloaded gradle/8.5/gradle-8.5-bin.zip (132,519,731 bytes in 1.5s, 82.42 MB/s)",
  "details": "{\"taskName\": null}"
}
```

```json
{
  "id": 43,
  "timestamp": "2026-10-27 15:45:30",
  "level": "ERROR",
  "module": "download",
  "message": "Download failed for gradle/1.0-milestone-2a/gradle-1.0-milestone-2a-bin.zip: upstream returned 404",
  "details": "{\"taskName\": null}"
}
```

## API Endpoints

### Get Logs
```
GET /admin/logs?page=1&level=ERROR&module=download
```
Query params:
- `page`: Page number (default 1)
- `level`: Filter by level
- `module`: Filter by module name

### Clear Logs
```
POST /admin/logs/clear
```
Returns redirect to `/admin/logs`

## Filtering UI

### Filter Controls
```html
<form method="get" class="filter-form">
  <select name="level">
    <option value="">All Levels</option>
    <option value="DEBUG">DEBUG</option>
    <option value="INFO">INFO</option>
    <option value="WARNING">WARNING</option>
    <option value="ERROR">ERROR</option>
    <option value="CRITICAL">CRITICAL</option>
  </select>
  
  <select name="module">
    <option value="">All Modules</option>
    <option value="download">download</option>
    <option value="tracker">tracker</option>
    ...
  </select>
  
  <button type="submit" class="btn btn-primary">Filter</button>
  <a href="{{ url_for('admin.logs') }}" class="btn">Reset</a>
</form>
```

### Results Table
| Column | Description |
|--------|-------------|
| Time | ISO timestamp |
| Level | Color-coded badge |
| Module | Module name |
| Message | Truncated message |
| Details | Click "View" for JSON details |

## Clear Logs

```bash
# Via UI
# Click "Clear All Logs" button (with confirmation)

# Via API
curl -X POST http://localhost/admin/logs/clear \
  -H "Cookie: cache_admin=..."
```

### SQL
```sql
DELETE FROM log_entries;
```

## Log Retention

No automatic rotation - manual clearing required. Consider:
- Regular cron job to clean old entries
- Or implement retention policy in background task

## Example Queries

### Recent Errors
```sql
SELECT * FROM log_entries 
WHERE level = 'ERROR' 
ORDER BY timestamp DESC LIMIT 50;
```

### Errors by Module
```sql
SELECT module, COUNT(*) as count
FROM log_entries 
WHERE level = 'ERROR'
GROUP BY module
ORDER BY count DESC;
```

### Slow Downloads
```sql
SELECT * FROM log_entries
WHERE module = 'download' 
  AND message LIKE '%MB/s%'
  AND CAST(json_extract(details, '$.speed_mbps') AS REAL) < 1
ORDER BY timestamp DESC;
```

## Integration with Tracker

The tracker events are also logged to the database via the `DBLogHandler`. The tracker events have:
- `module`: "tracker", "download", "serve", "probe"
- `details`: Full event details as JSON

## Security

- Logs are only accessible to authenticated admin users
- No sensitive data (passwords, tokens) in logs
- CSRF protection on clear action