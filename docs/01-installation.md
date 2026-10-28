# Installation & Setup

## Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **Port 80** available on host
- **At least 2GB RAM** available
- **Disk space**: Minimum 10GB (more for cache)

## Quick Start

```bash
# Clone and navigate
cd /home/ahaququq/Dokumenty/Yapping/PyCache

# Build and start
docker compose up -d --build

# Verify
curl http://localhost/health
# {"status":"ok","cache_max_bytes":17179869184}
```

## Docker Compose Configuration

The `docker-compose.yml` defines:

```yaml
services:
  pycache:
    build: .
    restart: unless-stopped
    ports:
      - "80:80"
    environment:
      CACHE_MAX_BYTES: 16G
      DATA_DIR: /app/app/data
      MODULES_DIR: /app/app/modules
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

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_MAX_BYTES` | `16G` | Max cache size |
| `CACHE_EVICTION_THRESHOLD` | `0.9` | Eviction trigger (90%) |
| `CACHE_EVICTION_TARGET` | `2G` | Target to free during eviction |
| `CACHE_MIN_FREE` | `512M` | Min free disk space |
| `UPSTREAM_TIMEOUT` | `120` | Upstream request timeout (s) |
| `MAX_REDIRECTS` | `10` | Max redirect hops |
| `DNS_1` | `1.1.1.1` | Primary DoH DNS |
| `DNS_2` | `8.8.8.8` | Secondary DoH DNS |

## First-Time Setup

1. **Start the container:**
   ```bash
   docker compose up -d --build
   ```

2. **Wait for health check:**
   ```bash
   curl http://localhost/health
   # {"status":"ok","cache_max_bytes":17179869184}
   ```

3. **Access the application:**
   - Main: `http://localhost/`
   - Admin: `http://localhost/admin/`

4. **First-time admin setup:**
   - Visit `http://localhost/admin/setup`
   - Create admin user (only accessible from localhost)
   - Or use default: `ahaququq` / `testpass`

## Directory Structure

```
/home/ahaququq/Dokumenty/Yapping/PyCache/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── routes/              # Flask blueprints
│   ├── modules/             # Source modules (Gradle, DB)
│   ├── templates/           # Jinja2 templates
│   ├── static/              # CSS/JS assets
│   └── ...                  # Core modules
├── nginx/
│   ├── nginx.conf
│   └── conf.d/
├── docs/                    # This documentation
├── test-gradle-project/     # Gradle integration test
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── docker-entrypoint.sh
```

## Verification

```bash
# Check health
curl http://localhost/health

# Check tracker
curl http://localhost/admin/tracker

# Check logs
docker compose logs -f pycache
```

## Persistence

Data is stored in Docker volumes:
- `cache-data` → `/app/app/cache` (cached files)
- `app-data` → `/app/app/data` (SQLite database)

These survive container restarts and rebuilds.

## Upgrading

```bash
docker compose down
git pull
docker compose up -d --build
```

## Uninstall

```bash
docker compose down -v  # -v removes volumes
```