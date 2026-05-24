FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps kept minimal: build-essential is only needed for numpy wheels
# on linux/arm64 where pre-built wheels lag behind. We strip it in the final
# stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --upgrade pip \
    && pip install ".[postgres]"

ENV CONET_DATA_DIR=/var/lib/conet-tactile \
    CONET_DATABASE_URL=sqlite+aiosqlite:////var/lib/conet-tactile/conet_tactile.db \
    CONET_LOG_JSON=true \
    CONET_ENVIRONMENT=prod \
    CONET_AUTH_REQUIRED=true

RUN mkdir -p /var/lib/conet-tactile/baselines

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
