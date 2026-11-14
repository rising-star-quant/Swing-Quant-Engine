FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# Create non-root system user and group for Cloud Run security compliance
RUN groupadd --system --gid 10001 appgroup && \
    useradd --system --uid 10001 --gid appgroup --create-home --shell /usr/sbin/nologin appuser

# Install minimal runtime dependencies in cached layer
COPY requirements-api.txt /app/requirements-api.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements-api.txt

# Copy application source and configuration
COPY api /app/api
COPY src /app/src
COPY config /app/config
COPY data /app/data

# Ensure local fallback data directory is writable by non-root appuser
RUN mkdir -p /app/data/users && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=3)" || exit 1

CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --proxy-headers"]
