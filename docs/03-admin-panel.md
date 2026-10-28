# Admin Panel

## Access

| URL | Description |
|-----|-------------|
| `http://localhost/admin/` | Main admin dashboard |
| `http://localhost/admin/tracker` | Live tracker |
| `http://localhost/admin/logs` | Event log viewer |
| `http://localhost/admin/cache` | Cache management |

## First-Time Setup

1. Visit `http://localhost/admin/setup`
2. Create admin user (only from localhost: `127.0.0.1`, `::1`)
3. Use credentials to login

## Default Credentials

If already set up:
- **Username**: `ahaququq`
- **Password**: `testpass`

## Dashboard (`/admin/`)

The dashboard shows:
- **Cache Stats**: Used space, limit, file count, free space
- **Modules**: Loaded modules with status (healthy/error/disabled)
- **Sources**: Configured sources with enable/disable
- **Quick Actions**: Links to cache, browse by path/source

## Live Tracker (`/admin/tracker`)

### Stats Panel
- **Active Downloads**: Currently downloading files
- **Active Serves**: Files being served
- **Total Events**: Session event count
- **Errors**: Error count
- **Connection Status**: Green=connected, Red=disconnected

### Progress Bars
- **Max 5 visible** (configurable)
- **Scrollable** for more than 5
- **Shows**: Path, percentage, bytes, speed, duration
- **Colors**: Blue=active, Green=complete, Red=error

### Event Log
- **Filters**: By type (download/serve/probe) and text search
- **Columns**: Time, Type, Message
- **Click**: View details (JSON)
- **Clear View**: Button to reset filter

## Log Viewer (`/admin/logs`)

### Features
- **Pagination**: 100 entries per page
- **Filters**: Level (DEBUG/WARNING/ERROR/CRITICAL), Module
- **Pagination**: Previous/Next pages
- **Clear Logs**: Button to delete all entries

### Filter Options
| Filter | Values |
|--------|--------|
| Level | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| Module | download, tracker, cache, sources, etc. |

### Log Entry Format
```json
{
  "id": 1,
  "timestamp": "2026-10-27 15:45:27",
  "level": "INFO",
  "module": "download",
  "message": "Downloaded gradle/8.5/gradle-8.5-bin.zip (132519731 bytes)",
  "details": {"taskName": null}
}
```

## Cache Management (`/admin/cache`)

### Cache Stats
- **Used**: Current cache size
- **Limit**: `CACHE_MAX_BYTES` (default 16G)
- **Files**: Number of cached files
- **Free**: Available disk space

### Actions
| Action | Description |
|--------|-------------|
| **Purge** | Delete all cached files, reset DB flags |
| **Config** | View cache limits (read-only) |

### Purge Operation
1. Click "Purge Cache"
2. Confirms deletion of all cached files
3. Updates DB: `cached=0, cache_path=NULL`

## Module Management (`/admin/modules`)

### Features
- **List**: All loaded modules with status
- **View**: Source code with Monaco editor
- **Edit**: Modify module code
- **Create**: New module from scratch
- **Reload**: Hot-reload all modules

### Module Status
| Status | Meaning |
|--------|---------|
| ✅ Healthy | Loaded successfully |
| ❌ Error | Load failed (see error) |
| ⏸ Disabled | Module disabled |

### Module Editor
- **Monaco Editor** with Python syntax highlighting
- **Syntax validation** before save
- **Hot reload** on save

## Source Management (`/admin/sources`)

### Source Types
| Kind | Module | Description |
|------|--------|-------------|
| `gradle` | `app.modules.gradle` | Gradle distributions |
| `db` | `app.modules.db` | DB-backed mappings |

### Source Actions
| Action | Description |
|--------|-------------|
| **New** | Create source (name, kind, config) |
| **Edit** | Modify name, kind, config, enabled |
| **Delete** | Remove source |
| **Mappings** | DB source: add/edit/delete mappings |

### DB Source Mappings
For `db` kind sources:
- **Local path** → **Remote URL** mappings
- **Enable/Disable** individual mappings
- **Add/Edit/Delete** mappings

## Cache Configuration (`/admin/cache/config`)

### Settings (Read-Only)
| Setting | Default | Description |
|---------|---------|-------------|
| Max Cache Size | 16G | `CACHE_MAX_BYTES` |
| Eviction Threshold | 90% | `CACHE_EVICTION_THRESHOLD` |
| Eviction Target | 2G | `CACHE_EVICTION_TARGET` |
| Min Free Space | 512M | `CACHE_MIN_FREE` |

> **Note**: Changes require container restart via environment variables.

## Source Configuration

### Gradle Source
```json
{
  "index_url": "https://services.gradle.org/distributions/"
}
```

### DB Source
```json
{
  "mappings": [
    {"local_path": "my/file.zip", "remote_url": "https://example.com/file.zip"}
  ]
}
```

## Security

### Authentication
- **Cookie-based**: `cache_admin` cookie
- **HTTPOnly**: Yes
- **SameSite**: Lax
- **Secure**: False (HTTP)
- **Max Age**: 7 days

### First-Time Setup
1. Visit `http://localhost/admin/setup`
2. Create username/password
3. Only accessible from localhost (`127.0.0.1`, `::1`)

### CSRF Protection
- **Token length**: 32 bytes
- **Per-request**: Generated via `make_csrf_token()`
- **Validated**: On POST requests

## Session Management

| Setting | Value |
|---------|-------|
| Cookie Name | `cache_admin` |
| Max Age | 7 days |
| HttpOnly | Yes |
| Secure | No (HTTP) |
| SameSite | Lax |
| Path | `/` |

## Admin Navigation

| Link | URL |
|------|-----|
| Dashboard | `/admin/` |
| Live Tracker | `/admin/tracker` |
| Logs | `/admin/logs` |
| Cache | `/admin/cache` |
| Modules | `/admin/modules` |
| Sources | `/admin/sources` |
| Cache Config | `/admin/cache/config` |
| Logout | `/admin/logout` |