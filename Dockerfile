# Multi-stage build for a minimal final image
# Build stage: install Python deps
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Runtime stage: minimal image with nginx + Python
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/app/.local/bin:${PATH}"

# Install nginx and runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r app && useradd -r -g app -d /home/app -s /bin/bash app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/app/.local

# Copy application code
WORKDIR /app
COPY --chown=app:app app ./app
COPY --chown=app:app wsgi.py .
COPY --chown=app:app nginx/nginx.conf /etc/nginx/nginx.conf
COPY --chown=app:app nginx/conf.d/cache.conf /etc/nginx/conf.d/cache.conf

# Create cache and data directories
RUN mkdir -p /app/cache /app/data /app/modules && chown -R app:app /app/cache /app/data /app/modules

# Nginx dirs
RUN mkdir -p /var/cache/nginx /var/log/nginx && chown -R app:app /var/cache/nginx /var/log/nginx

# Switch to non-root
USER app

# Expose HTTP
EXPOSE 80

# Entrypoint: start nginx + gunicorn
COPY --chown=app:app docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]