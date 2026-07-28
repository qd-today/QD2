# QD2 Multi-stage Dockerfile
# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build

WORKDIR /app/qd-web
COPY qd-web/package.json qd-web/package-lock.json* ./
RUN npm ci
COPY qd-web/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim AS backend

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy the locked workspace and install it
COPY pyproject.toml uv.lock ./
COPY qd-core/ ./qd-core/
COPY qd-cli/ ./qd-cli/
COPY qd-server/ ./qd-server/
RUN uv sync --frozen --no-dev --all-packages

# Copy frontend build
COPY --from=frontend-build /app/qd-web/dist ./qd-web/dist

# Expose port
ENV QD_PORT=8080
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run server
CMD ["uv", "run", "--frozen", "--no-dev", "qd-server"]
