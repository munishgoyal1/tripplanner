# syntax=docker/dockerfile:1

# --- Stage 1: build the React SPA --------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /web
ARG NPM_REGISTRY=https://ms-feed-2.pkgs.visualstudio.com/1es-public/_packaging/npm-public/npm/registry/
COPY frontend/package.json frontend/package-lock.json ./
COPY packages/tripplanner-client/ /packages/tripplanner-client/
RUN npm ci --include=dev \
    --registry=${NPM_REGISTRY} \
    --replace-registry-host=always
COPY frontend/ ./
RUN npm run build   # emits /web/dist

# --- Stage 2: Python runtime -------------------------------------------------
FROM python:3.12-slim

ARG PYTHON_PACKAGE_INDEX=https://ms-feed-2.pkgs.visualstudio.com/1es-public/_packaging/pypi-public/pypi/simple/

# Link this image to the source repo so GHCR auto-grants the repo's Actions
# workflow push access (avoids `denied: write_package` on CI runs).
LABEL org.opencontainers.image.source="https://github.com/munishgoyal1/tripplanner"
LABEL org.opencontainers.image.description="AI trip planner — React SPA + FastAPI + LangGraph"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=5 \
    SPA_DIST_DIR=/app/frontend/dist

WORKDIR /app

# Resolve third-party dependencies from package metadata before copying the
# application. Source-only edits can then reuse this expensive layer.
COPY pyproject.toml ./
COPY src/tripplanner/__init__.py src/tripplanner/__init__.py
RUN PIP_INDEX_URL=${PYTHON_PACKAGE_INDEX} pip install --no-cache-dir "."

COPY src/ src/
COPY frontend/src/publicEntry/publicDemoRuns.json src/tripplanner/public_demo_runs.json
RUN PIP_INDEX_URL=${PYTHON_PACKAGE_INDEX} pip install --no-cache-dir --no-deps --force-reinstall "."

# Built SPA from stage 1 — served by FastAPI at the root origin.
COPY --from=frontend /web/dist ./frontend/dist

EXPOSE 8000

# Uvicorn serves both the API and the static SPA on one port.
CMD ["uvicorn", "tripplanner.api:app", "--host", "0.0.0.0", "--port", "8000"]

