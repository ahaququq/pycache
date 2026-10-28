# Configuration Reference

## Environment Variables

All configuration is done via environment variables in `docker-compose.yml` or container environment.

## Cache Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_MAX_BYTES` | `16G` | Maximum total cache size |
| `CACHE_EVICTION_THRESHOLD` | `0.9` | Eviction trigger (90% of max) |
| `CACHE_EVICTION_TARGET` | `2G` | Bytes to free during eviction |
| `CACHE_MIN_FREE` | `512M` | Minimum free disk space |

### Size Format

| Suffix | Multiplier |
|--------|------------|
| `K` | 1,024 |
| `M` | 1,024² |
| `G` | 1,024³ |
| `T` | 1,024⁴ |

Examples: `16G`, `512M`, `1073741824` (bytes)

## Network / Upstream

| Variable | Default | Description |
|----------|---------|-------------|
| `UPSTREAM_TIMEOUT` | `120` | Request timeout (seconds) |
| `MAX_REDIRECTS` | `10` | Max redirect hops |
| `UPSTREAM_USER_AGENT` | `cache-server/1.0` | HTTP User-Agent |

## DNS Configuration

### Docker Compose DNS
```yaml
services:
  pycache:
    dns:
      - 1.1.1.1
      - 8.8.8.8
```

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `DNS_1` | `1.1.1.1` | Primary DoH DNS |
| `DNS_2` | `8.8.8.8` | Secondary DoH DNS |

## Server Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8000` | Flask port |
| `PUBLIC_BASE_URL` | `""` | Public URL (for redirects) |
| `DEBUG` | `false` | Debug mode |
| `LOG_LEVEL` | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |

## Admin / Auth

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_COOKIE_NAME` | `cache_admin` | Session cookie name |
| `ADMIN_COOKIE_MAX_AGE` | `604800` (7 days) | Cookie lifetime |
| `CSRF_TOKEN_LENGTH` | `32` | CSRF token bytes |

## Module Loading

| Variable | Default | Description |
|----------|---------|-------------|
| `MODULE_MAX_RELOAD_FAILURES` | `3` | Max reload retries |
| `MODULE_RELOAD_INTERVAL` | `5` | Reload check interval (s) |

## Module Directory

| Variable | Default | Description |
|----------|---------|-------------|
| `MODULES_DIR` | `/app/app/modules` | Module directory path |

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/app/app/data` | Database directory |

## Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_DIR` | `/app/app/cache` | File cache directory |
| `DATA_DIR` | `/app/app/data` | Database directory |

## Complete docker-compose.yml Example

```yaml
version: '3.8'

services:
  pycache:
    build: .
    restart: unless-stopped
    ports:
      - "80:80"
    environment:
      # Cache
      CACHE_MAX_BYTES: 16G
      CACHE_EVICTION_THRESHOLD: 0.9
      CACHE_EVICTION_TARGET: 2G
      CACHE_MIN_FREE: 512M
      
      # Network
      UPSTREAM_TIMEOUT: 120
      MAX_REDIRECTS: 10
      UPSTREAM_USER_AGENT: "pycache/1.0"
      
      # DNS
      DNS_1: 1.1.1.1
      DNS_2: 8.8.8.8
      
      # Server
      HOST: 127.0.0.1
      PORT: 8000
      LOG_LEVEL: INFO
      
      # Admin
      ADMIN_COOKIE_MAX_AGE: 604800
      CSRF_TOKEN_LENGTH: 32
      
      # Modules
      MODULE_MAX_RELOAD_FAILURES: 3
      MODULE_RELOAD_INTERVAL: 5
      MODULES_DIR: /app/app/modules
      
      # Paths
      DATA_DIR: /app/app/data
      CACHE_DIR: /app/app/cache

    volumes:
      - cache-data:/app/app/cache
      - app-data:/app/app/data
    dns:
      - 1.1.1.1
      - 8.8.8.8

volumes:
  cache-data:
  app-data:
```

## Programmatic Configuration (app/config.py)

### Key Functions

```python
def _env_bool(name: str, default: bool) -> bool:
    """Parse boolean from environment."""
    
def _env_int(name: str, default: int) -> int:
    """Parse integer from environment."""
    
def _env_bytes(name: str, default: int) -> int:
    """Parse human-readable size (16G, 512M, etc.)."""
```

### Key Config Objects

```python
# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.environ.get("CACHE_DIR", str(APP_DIR / "cache")))
DATA_DIR = Path(os.environ.get("DATA_DIR", str(APP_DIR / "data")))
MODULES_DIR = Path("/app/app/modules")
DB_PATH = DATA_DIR / "cache_server.db"

# Cache limits
CACHE_MAX_BYTES = _env_bytes("CACHE_MAX_BYTES", 16 * 1024**3)
CACHE_EVICTION_THRESHOLD = float(os.environ.get("CACHE_EVICTION_THRESHOLD", "0.9"))
CACHE_EVICTION_TARGET = _env_bytes("CACHE_EVICTION_TARGET", 2 * 1024**3)
CACHE_MIN_FREE = _env_bytes("CACHE_MIN_FREE", 512 * 1024**2)

# Network
UPSTREAM_TIMEOUT = _env_int("UPSTREAM_TIMEOUT", 120)
MAX_REDIRECTS = _env_int("MAX_REDIRECTS", 10)
UPSTREAM_USER_AGENT = os.environ.get("UPSTREAM_USER_AGENT", "cache-server/1.0")

# Server
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = _env_int("PORT", 8000)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

# Admin
ADMIN_COOKIE_NAME = "cache_admin"
ADMIN_COOKIE_MAX_AGE = _env_int("ADMIN_COOKIE_MAX_AGE", 86400 * 7)
CSRF_TOKEN_LENGTH = 32

# Modules
MODULE_MAX_RELOAD_FAILURES = _env_int("MODULE_MAX_RELOAD_FAILURES", 3)
MODULE_RELOAD_INTERVAL = _env_int("MODULE_RELOAD_INTERVAL", 5)

# Misc
DEBUG = _env_bool("DEBUG", False)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
```

## Runtime Configuration

### Changing Settings at Runtime

Most settings require container restart. However, some can be changed via:

1. **Admin Panel**: Cache settings, source config
2. **Database**: Source configs, unavailable flags
3. **Hot reload**: Module code changes (5s interval)

### Runtime-Only Settings

| Setting | Change Method |
|---------|---------------|
| Source config | Admin panel → Sources |
| Module code | Edit file → auto-reload |
| Cache purge | Admin panel → Cache → Purge |
| Log level | Requires restart |

## Validation

### Startup Checks

The application validates on startup:

```python
# In config.py
for _d in (CACHE_DIR, DATA_DIR, MODULES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Directory permissions checked at startup
```

### Runtime Validation

```python
# In downloader.py
if not CACHE_DIR.exists():
    raise RuntimeError("Cache directory not found")

if not CACHE_DIR.is_dir():
    raise RuntimeError("Cache path is not a directory")
```

## Configuration Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Container orchestration |
| `app/config.py` | Python configuration |
| `nginx/conf.d/cache.conf` | Nginx reverse proxy |
| `nginx/nginx.conf` | Nginx main config |
| `Dockerfile` | Container build |

## Override Examples

### Development
```yaml
environment:
  DEBUG: "true"
  LOG_LEVEL: DEBUG
  CACHE_MAX_BYTES: 1G
```

### Production
```yaml
environment:
  CACHE_MAX_BYTES: 100G
  CACHE_EVICTION_THRESHOLD: 0.85
  CACHE_EVICTION_TARGET: 10G
  CACHE_MIN_FREE: 10G
  LOG_LEVEL: WARNING
  UPSTREAM_TIMEOUT: 300
```

### Testing
```yaml
environment:
  CACHE_MAX_BYTES: 100M
  CACHE_EVICTION_THRESHOLD: 0.5
  UPSTREAM_TIMEOUT: 30
  LOG_LEVEL: DEBUG
```

## Validation

### Required Variables

None strictly required (all have defaults).

### Recommended Minimum

```yaml
environment:
  CACHE_MAX_BYTES: 10G
  DNS_1: 1.1.1.1
  DNS_2: 8.8.8.8
```

### Size Limits

| Setting | Min | Max |
|---------|-----|-----|
| `CACHE_MAX_BYTES` | 100M | 100T |
| `CACHE_EVICTION_THRESHOLD` | 0.1 | 0.99 |
| `CACHE_EVICTION_TARGET` | 10M | `CACHE_MAX_BYTES` |
| `CACHE_MIN_FREE` | 10M | 10G |

## Validation in Code

```python
# app/config.py
def _env_bytes(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    raw = raw.strip().upper()
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    if raw[-1] in units:
        try:
            return int(float(raw[:-1]) * units[raw[-1]])
        except ValueError:
            return default
    try:
        return int(raw)
    except ValueError:
        return default
```

## Docker Compose Override

### Development Override

Create `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  pycache:
    environment:
      DEBUG: "true"
      LOG_LEVEL: DEBUG
      CACHE_MAX_BYTES: 1G
    volumes:
      - ./app:/app/app  # Live code reload
    ports:
      - "8000:8000"  # Direct Flask access
```

Usage:
```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

## Configuration Precedence

1. **docker-compose.yml** (highest)
2. **docker-compose.override.yml**
3. **Environment variables**
4. **Default values** (in config.py)

## Validation Script

```bash
#!/bin/bash
# validate-config.sh

echo "Checking configuration..."

# Check required dirs
for dir in /app/app/cache /app/app/data /app/app/modules; do
    if [ ! -d "$dir" ]; then
        echo "ERROR: Missing directory $dir"
        exit 1
    fi
done

# Check DB
sqlite3 /app/app/data/cache_server.db ".tables" || exit 1

# Check DNS
dig @1.1.1.1 services.gradle.org +short || exit 1

echo "Configuration OK"
```

Run in container:
```bash
docker compose exec pycache /bin/bash /app/validate-config.sh
```