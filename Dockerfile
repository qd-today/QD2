# QD2 Multi-stage Dockerfile
# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build

WORKDIR /app/qd-web
COPY qd-web/package.json qd-web/package-lock.json* ./
RUN npm install
COPY qd-web/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim AS backend

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace files
COPY pyproject.toml ./
COPY qd-core/pyproject.toml ./qd-core/
COPY qd-cli/pyproject.toml ./qd-cli/
COPY qd-server/pyproject.toml ./qd-server/

# Install dependencies
RUN uv sync --no-dev --all-packages

# Copy source code
COPY qd-core/ ./qd-core/
COPY qd-cli/ ./qd-cli/
COPY qd-server/ ./qd-server/

# Copy frontend build
COPY --from=frontend-build /app/qd-web/dist ./qd-server/src/qd_server/static

# Install packages
RUN uv sync --no-dev --all-packages

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run server
CMD ["uv", "run", "qd-server"]
