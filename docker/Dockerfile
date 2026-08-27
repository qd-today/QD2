# syntax=docker/dockerfile:1.7

FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend-build

WORKDIR /app/qd-web
COPY qd-web/package.json qd-web/package-lock.json* ./
RUN npm ci
COPY qd-web/ ./
RUN npm run build

FROM python:3.12-slim AS python-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cargo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY qd-core/ ./qd-core/
COPY qd-cli/ ./qd-cli/
COPY qd-server/ ./qd-server/
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels ./qd-core ./qd-cli ./qd-server

FROM python:3.12-slim AS runtime

WORKDIR /app
COPY --from=python-build /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels qd-cli qd-server \
    && rm -rf /wheels

# qd_server.app resolves bundled frontend assets from this installation-relative path.
COPY --from=frontend-build /app/qd-web/dist /usr/local/lib/qd-web/dist

EXPOSE 8923

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:' + os.getenv('QD_PORT', '8923') + '/health')"

CMD ["qd-server"]
