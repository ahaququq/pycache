# PyCache - Overview

## What is PyCache?

PyCache is a **Dockerized Nginx + Python modular caching server** that serves as a caching proxy for file distributions, particularly designed for **Gradle distributions** but extensible to other file sources.

## Key Features

| Feature | Description |
|---------|-------------|
| **Caching Proxy** | Proxies file requests, caching files locally on first download |
| **Modular Source System** | Pluggable source modules (Gradle, Maven, DB-backed, etc.) |
| **Live Tracker** | Real-time dashboard with progress bars and event log |
| **DoH DNS Resolution** | DNS over HTTPS via Cloudflare (1.1.1.1) and Google (8.8.8.8) |
| **Unavailable File Handling** | Tags unavailable files with error reasons |
| **Admin Panel** | Web-based management with live tracker and logs |
| **Download Notifications** | Real-time progress bars with speed/percentage |
| **Cache Persistence** | SQLite-backed metadata with file-based storage |

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Client        │────▶│   Nginx (Port 80)│────▶│  Flask/Gunicorn  │
│   (Gradle,      │     │  (Reverse Proxy) │     │  (Port 8000)     │
│   Browser)      │     │                  │     │  (Python/Flask)  │
└─────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                          │
                    ┌──────────────────────────────────────┤
                    ▼              ▼            ▼          ▼
              ┌─────────────────────────────────────────────────┐
              │              Flask Application                   │
              │  ┌─────────┐ ┌─────────┐ ┌─────────┐           │
              │  │ Public  │ │  Admin  │ │   API   │           │
              │  │  Routes │ │  Routes │ │  Routes │           │
              │  └─────────┘ └─────────┘ └─────────┘           │
              └──────────────┬────────────────────┬─────────────┘
                             │                    │
                    ┌────────┴────────┐    ┌──────┴──────┐
                    ▼                 ▼    ▼             ▼
              ┌───────────┐    ┌───────────┐  ┌────────────────┐
              │  SQLite   │    │  Files    │  │  Modules       │
              │  (SQLite) │    │  (Cache)  │  │  (Gradle, etc.)│
              └───────────┘    └───────────┘  └────────────────┘
```

## Core Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Flask App** | `app/__init__.py` | Application factory, CSP, blueprints |
| **Public Routes** | `app/routes/public.py` | Cache proxy, info pages, probe |
| **Admin Routes** | `app/routes/admin.py` | Dashboard, logs, cache mgmt |
| **API Routes** | `app/routes/api.py` | JSON endpoints (probe, download) |
| **Downloader** | `app/downloader.py` | Stream downloads with progress |
| **Tracker** | `app/tracker.py` | Live event streaming (SSE) |
| **Sources** | `app/sources.py` | Source manager (Gradle, DB) |
| **Modules** | `app/modules/` | Source implementations (Gradle, DB) |
| **Database** | `app/db.py` | SQLite with WAL mode |
| **Config** | `app/config.py` | Environment-based configuration |

## Quick Links

- [Installation & Setup](./01-installation.md)
- [Running the Application](./02-running.md)
- [Admin Panel Guide](./03-admin-panel.md)
- [Live Tracker](./04-live-tracker.md)
- [Download System](./05-download-system.md)
- [DoH DNS](./06-doh-dns.md)
- [Unavailable Files](./07-unavailable-files.md)
- [Log Viewer](./08-log-viewer.md)
- [Gradle Integration](./09-gradle-integration.md)
- [System-Wide Gradle Setup](./14-gradle-system-wide.md)
- [Configuration](./10-configuration.md)
- [API Reference](./11-api-reference.md)
- [Troubleshooting](./12-troubleshooting.md)

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Reverse Proxy** | Nginx |
| **Application Server** | Gunicorn + Flask |
| **Language** | Python 3.12+ |
| **Database** | SQLite (WAL mode) |
| **DNS** | DoH (Cloudflare 1.1.1.1, Google 8.8.8.8) |
| **Frontend** | Vanilla JS, CSS, Jinja2 templates |
| **Real-time** | Server-Sent Events (SSE) |
| **Container** | Docker + Docker Compose |
| **Reverse Proxy** | Nginx |
| **Container Runtime** | Docker |