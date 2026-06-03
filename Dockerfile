# syntax=docker/dockerfile:1

# --- Stage 1: build the React SPA --------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # emits /web/dist

# --- Stage 2: Python runtime -------------------------------------------------
FROM python:3.12-slim

# Link this image to the source repo so GHCR auto-grants the repo's Actions
# workflow push access (avoids `denied: write_package` on CI runs).
LABEL org.opencontainers.image.source="https://github.com/munishgoyal1/multiagent"
LABEL org.opencontainers.image.description="AI trip planner — React SPA + FastAPI + LangGraph"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SPA_DIST_DIR=/app/frontend/dist

WORKDIR /app

# Install deps first (layer-cache friendly)
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir "."

# Built SPA from stage 1 — served by FastAPI at the root origin.
COPY --from=frontend /web/dist ./frontend/dist

EXPOSE 8000

# Uvicorn serves both the API and the static SPA on one port.
CMD ["uvicorn", "multiagent.api:app", "--host", "0.0.0.0", "--port", "8000"]
