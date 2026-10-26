# PyCache Dockerized Nginx + Python Caching Server

## Overview

A modular caching proxy server that sits between HTTP clients and upstream distribution sources. Nginx acts as the front-end proxy with configurable cache eviction, while a Python Flask application handles source resolution, download, and caching logic.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx (Port 80)                              │
│  • Caching proxy with LRU eviction                                │
│  • Redirect following & final payload caching                     │
│  • Admin panel behind password auth                               │
│  • Static file serving                                            │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Gunicorn (Python)                              │
│  • Flask app with modular source system                           │
│  • SQLite DB (WAL mode) for metadata                              │
│  • Module isolation with crash protection                         │
│  • Configurable cache limits (16 GiB default)                   │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    On-Disk Cache                                   │
│  • SHA-256 named files (stable, collision-free)                   │
│  • LRU eviction based on access time                              │
│  • Configurable max size + min free space floor                   │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

### HTTP Caching Proxy
- Nginx caches frequently used files, evicts least-recently-used when limit reached
- Configurable cache size limit (16 GiB default, set via `CACHE_MAX_BYTES`)
- Minimum free disk space floor to prevent OOM
- Files fetched from upstream on cache miss, cached atomically

### Python Module System
- Each module lives in `app/modules/` and derives from `ModuleBase`
- Modules expose: `list_items()`, `resolve()`, `probe()`, optional `get_config_schema()`
- Module isolation: each loaded in its own import namespace
- Crash protection: bad modules count failures; after 3 failures module disabled
- Reload on file change via background watchdog thread

### Built-in Modules
- **gradle**: Enumerates all published Gradle distributions from `services.gradle.org`, maps paths like `gradle/8.5/gradle-8.5-bin.zip` to remote URLs. Enables local Gradle installs to point at the cache.
- **db**: Generic "database source" backed by the `mappings` table. Mappings can be added/edited via the admin panel for on-the-fly URL->path mapping.

### Source Management
- Sources stored in SQLite `sources` table: name, kind (module name), JSON config, enabled flag
- Admin can create new sources with any module kind
- DB-backed sources allow quick on-the-fly mappings without code

### Admin Panel (`/admin`)
- **Authentication**: First connection from localhost without an admin account allows one-time setup
- **Password**: First admin set on first localhost connection; subsequent access requires password
- **Source management**: Create/edit/delete sources, configure module settings
- **DB mappings**: For `db` kind sources, add/remove local_path -> remote_url mappings
- **Module editor**: In-browser Monaco editor for creating/editing modules with syntax validation
- **Cache control**: Purge cache, view stats, configure limits
- **Dark mode**: Respects `prefers-color-scheme`, persistent via localStorage

### API Endpoints (`/api`)
- `POST /api/probe`: Check if a local path exists upstream
- `POST /api/download`: Force download a path into cache
- `POST /api/reload`: Reload modules and sources

### Info Pages (`/info`)
- `/info/by-path`: All files grouped by local path with caching status
- `/info/by-source`: Files grouped by source with caching stats
- `/info/by-source/<id>`: Detailed view per source

### Gradle Use Case
Local Gradle environments can be configured to use the cache:

```bash
export GRADLE_USER_HOME=/path/to/cache/gradle
# Or in gradle.properties:
systemProp.gradle.user.home=/path/to/cache/gradle
```

The server will cache all published Gradle distributions (`gradle-8.5-bin.zip`, etc.), so `./gradlew build` downloads once and serves cached copies thereafter.

### Nginx Configuration
- Proxy to gunicorn on port 8000
- Buffering for large file downloads
- Security headers
- Static file serving with far-future caching
- Health check endpoint

### Docker
- Multi-stage build: builder (deps) + runtime (nginx + Python)
- Entrypoint starts nginx (foreground) + gunicorn (background)
- Environment variables for all configuration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_MAX_BYTES` | `16G` | Hard limit for total cache size |
| `CACHE_EVICTION_THRESHOLD` | `0.9` | Fraction of max at which eviction starts |
| `CACHE_EVICTION_TARGET` | `2G` | Bytes to free when eviction runs |
| `CACHE_MIN_FREE` | `512M` | Minimum free disk space for OS |
| `UPSTREAM_TIMEOUT` | `120` | Seconds for upstream HTTP operations |
| `MAX_REDIRECTS` | `10` | Max redirect chain length |
| `PORT` | `8000` | Gunicorn listen port |
| `HOST` | `127.0.0.1` | Bind address |
| `DEBUG` | `false` | Flask debug mode |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Project Structure

```
PyCache/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # All configuration from env vars
│   ├── db.py                # SQLite database layer
│   ├── auth.py              # Password hashing, session cookies
│   ├── cache.py             # LRU on-disk cache manager
│   ├── downloader.py        # HTTP download with redirect following
│   ├── modules/
│   │   ├── __init__.py      # Package init
│   │   ├── _loader.py       # Module loader with isolation
│   │   ├── base.py          # ModuleBase, Item, ModuleInfo
│   │   ├── gradle.py        # Built-in Gradle module
│   │   └── db.py            # Built-in DB source module
│   ├── routes/
│   │   ├── __init__.py      # Blueprint registration
│   │   ├── public.py        # Public routes (proxy, info pages)
│   │   ├── admin.py         # Admin panel with auth
│   │   └── api.py           # JSON API endpoints
│   └── templates/
│       ├── base.html        # Base layout with dark mode
│       ├── index.html       # Landing page
│       ├── by_path.html   # Files by path
│       ├── by_source.html # Sources summary
│       ├── by_source_detail.html # Per-source details
│       └── admin/
│           ├── dashboard.html
│           ├── setup.html
│           ├── login.html
│           ├── sources.html
│           ├── source_form.html
│           ├── mappings.html
│           ├── mapping_form.html
│           ├── modules.html
│           ├── module_view.html
│           ├── module_edit.html
│           ├── cache.html
│           └── cache_config.html
├── nginx/
│   ├── nginx.conf           # Main nginx config
│   └── conf.d/cache.conf    # Proxy config
├── Dockerfile               # Multi-stage build
├── docker-entrypoint.sh     # Start nginx + gunicorn
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Installation & Running

### Local Development (without Docker)

```bash
# Clone and enter directory
cd PyCache

# Create and activate venv
python3 -m venv .venv
source .venv/bin/activate

# Install deps
pip install flask sqlalchemy requests gunicorn

# Run
gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 2 wsgi:app
# Or: python wsgi.py (development only)
```

Access at `http://127.0.0.1:8000`

### Docker

```bash
docker build -t pycache .
docker run -p 80:80 \
  -e CACHE_MAX_BYTES=16G \
  -e DATA_DIR=/data \
  -v /path/to/cache:/app/cache \
  -v /path/to/data:/app/data \
  pycache
```

The container will:
1. Initialize the database
2. Load modules (gradle, db)
3. Start nginx on port 80
4. Start gunicorn serving the Flask app

## Administration

### First-time Setup
1. Run the container (or start local gunicorn)
2. Access `/admin` from `127.0.0.1`
3. Since no admin exists, the setup form appears
4. Create username/password
5. Subsequent logins require the password
6. Non-localhost connections are rejected until admin is set up

### Adding a New Source
1. Login to `/admin`
2. Go to "Sources" → "New Source"
3. Fill in name, select module kind
4. Configure module-specific fields if any
5. Click "Save"
6. For `db` kind sources, go to the source's "Mappings" tab to add local_path -> remote_url entries

### Adding a New Module
1. Login to `/admin`
2. Go to "Modules" → "New Module"
3. Write a class inheriting from `ModuleBase` with `list_items()` and `resolve()`
4. Syntax is validated before saving
5. Module is reloaded automatically

## Dark Mode

The UI supports dark mode natively:
- Respects `prefers-color-scheme` media query
- Toggle button in the topbar
- Preference persisted in `localStorage`
- All CSS variables switch between light/dark themes

## Key Takeaways

1. **Modular design**: New sources are added by writing Python modules, not by changing core code
2. **Crash isolation**: Modules load in isolation; a bad module counts failures and gets disabled, never crashes the server
3. **Config via env vars**: Almost all behavior is configurable through environment variables; no code changes needed for most tweaks
4. **SQLite for metadata**: Serverless, file-based DB that travels with the data directory; WAL mode for concurrent readers
5. **Nginx + Python split**: Nginx handles caching/proxying; Python handles source resolution and dynamic logic
6. **Admin-first security**: Admin panel is locked down until an admin account is created from localhost
7. **Dark mode by default**: UI respects system preferences out of the box
8. **Full redirect following**: Python downloads the final payload after any redirect chain, never just a redirect page
9. **LRU eviction with safety bounds**: Cache size is hard-limited; system never runs out of disk space
10. **Git-friendly**: Project split into many small files; branches can be created for features