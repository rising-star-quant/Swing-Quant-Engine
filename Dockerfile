# Stage 1: Build React / PWA Frontend Assets
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Python 3.11 FastAPI Single-Origin Server + Static GUI
FROM python:3.11-slim AS runtime

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

# Install runtime dependencies
COPY requirements.txt /app/requirements.txt
COPY requirements-api.txt /app/requirements-api.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt -r /app/requirements-api.txt

# Copy backend application source, configuration, and fallback seed data
COPY api /app/api
COPY src /app/src
COPY config /app/config
COPY data /app/data

# Copy compiled React/PWA static bundle from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/static_gui

# Ensure local fallback directories are writable by non-root appuser
RUN mkdir -p /app/data/state /app/data/users /app/data/portfolios /app/data/ohlcv_parquet && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3)" || exit 1

CMD ["sh", "-c", "exec uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --proxy-headers"]
