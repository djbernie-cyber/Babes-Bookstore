FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build stage: compile wheels so the runtime image stays slim
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# Runtime stage
FROM base AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . .

# Run as an unprivileged user
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# This image can run as either the API server or the background worker.
# Set PROCESS_TYPE=worker (or FLY_PROCESS_GROUP=worker for compatibility)
# to run Celery worker+beat. Default: run migrations and serve the API.
# Without the worker, paid customers would never receive their downloads.
CMD ["sh", "-c", "if [ \"$PROCESS_TYPE\" = \"worker\" ] || [ \"$FLY_PROCESS_GROUP\" = \"worker\" ]; then exec celery -A app.celery_app:celery_app worker --beat --loglevel=info --concurrency=${CELERY_CONCURRENCY:-2} --prefetch-multiplier=1; else python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'; fi"]
