# syntax=docker/dockerfile:1.6
#
# Production image. Replicates what nixpacks.toml does on Railway:
#   1. npm ci && npm run build  -> frontend/dist
#   2. pip install -r requirements.txt
#   3. uvicorn app.main:app, which serves the SPA from frontend/dist
#
# Dockerfile.dev stays as-is for local development (source mounted as a volume,
# no frontend build). This one is self-contained.

# --- Stage 1: build the React SPA -------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


# --- Stage 2: python dependencies into a venv -------------------------------
# Build toolchain lives here only; the runtime stage copies just the venv.
FROM python:3.12-slim AS pydeps

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libpq-dev \
        libcairo2-dev \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt


# --- Stage 3: runtime --------------------------------------------------------
FROM python:3.12-slim AS runtime

# Runtime libs only (libpq5/libcairo2), not the -dev headers.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libcairo2 \
        tzdata \
 && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Mexico_City

COPY --from=pydeps /opt/venv /opt/venv

WORKDIR /app
COPY . .

# Built SPA overwrites whatever frontend/dist is committed in the repo.
COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000

# PORT is honoured so this image also works on platforms that inject it
# (Railway sets it and routes to 8080). Defaults to 8000 for the VPS/Caddy setup.
# --proxy-headers so the app sees the real scheme/IP behind the proxy.
CMD ["sh", "-c", "python scripts/railway_init.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
