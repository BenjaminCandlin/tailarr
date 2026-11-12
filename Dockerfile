# Tailarr container image.
# Build: docker build -t tailarr .

# ---- 1. Build the web interface -------------------------------------------
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Install the Python app ---------------------------------------------
FROM python:3.12-slim-bookworm AS backend
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/venv
WORKDIR /src/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev --no-editable

# ---- 3. The final image ------------------------------------------------------
FROM python:3.12-slim-bookworm

# Pinned dovi_tool release (https://github.com/quietvoid/dovi_tool/releases).
ARG DOVI_TOOL_VERSION=2.3.4

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg mediainfo; \
    curl -fsSL https://mkvtoolnix.download/gpg-pub-moritzbunkus.gpg \
        -o /usr/share/keyrings/gpg-pub-moritzbunkus.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/gpg-pub-moritzbunkus.gpg] https://mkvtoolnix.download/debian/ bookworm main" \
        > /etc/apt/sources.list.d/mkvtoolnix.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends mkvtoolnix; \
    curl -fsSL "https://github.com/quietvoid/dovi_tool/releases/download/${DOVI_TOOL_VERSION}/dovi_tool-${DOVI_TOOL_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
        | tar -xz -C /usr/local/bin; \
    chmod 0755 /usr/local/bin/dovi_tool; \
    dovi_tool --version; mkvmerge --version; mediainfo --version; \
    apt-get purge -y --auto-remove curl gnupg; \
    rm -rf /var/lib/apt/lists/*

COPY --from=backend /app/venv /app/venv
COPY --from=frontend /src/frontend/dist /app/static
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

ENV PATH="/app/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOME=/config \
    PUID=99 \
    PGID=100 \
    UMASK=002 \
    TAILARR_PORT=8484 \
    TAILARR_CONFIG_DIR=/config \
    TAILARR_STATIC_DIR=/app/static \
    TAILARR_MOVIES_DIR=/data/media/movies \
    TAILARR_TV_DIR=/data/media/tv

VOLUME ["/config"]
EXPOSE 8484

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/ping' % os.environ.get('TAILARR_PORT','8484'), timeout=8)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "tailarr"]

LABEL org.opencontainers.image.title="Tailarr" \
      org.opencontainers.image.description="A friendly web front-end for MKVToolNix, for Unraid." \
      org.opencontainers.image.licenses="GPL-3.0-or-later"
