"""QD Server main application entry point.

Creates and configures the FastAPI application with all routes,
middleware, and database initialization.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qd_server.api import api_router
from qd_server.config import ensure_encryption_key, ensure_jwt_secret, get_settings

logger = logging.getLogger("qd2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    settings = get_settings()
    settings.ensure_config_dir()
    ensure_jwt_secret(settings)
    ensure_encryption_key(settings)

    from qd_server.api.data_management import apply_pending_database_restore

    restored_backup = await asyncio.to_thread(apply_pending_database_restore, settings)
    if restored_backup:
        logger.warning("Applied pending database restore; previous database saved to %s", restored_backup)

    # Initialize database tables
    from sqlmodel import SQLModel

    from qd_server.schema_migrations import upgrade_database_schema

    async with settings.db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        applied_migrations = await conn.run_sync(upgrade_database_schema)
    if applied_migrations:
        logger.info("Applied database schema upgrades: %s", ", ".join(applied_migrations))

    from qd_server.services.encryption import migrate_sensitive_storage

    protected_values = await migrate_sensitive_storage(settings)
    if protected_values:
        logger.info("Encrypted or rotated %d sensitive database values", protected_values)

    # Start scheduler
    from qd_server.services.scheduler import scheduler
    await scheduler.start()

    logger.info("QD2 Server started")

    yield

    # Shutdown
    from qd_server.services.scheduler import scheduler
    await scheduler.stop()
    await settings.db.engine.dispose()

    logger.info("QD2 Server stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="QD2 Server",
        description="HTTP Request Scheduled Task Automation Framework",
        version="25.1.0-dev",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict to frontend domain
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(api_router)

    # QD v1 compatible /util/* routes (no /api prefix — templates call them directly)
    from qd_server.api.util import router as util_router

    app.include_router(util_router, prefix="/util", tags=["Util"])

    # WebSocket routes (full path declared in router)
    from qd_server.api.ws import router as ws_router

    app.include_router(ws_router)

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "25.1.0-dev"}

    # Serve frontend static files (qd-web/dist) if present
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist_dir = Path(__file__).resolve().parents[3] / "qd-web" / "dist"
    if dist_dir.exists():
        app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            # Defense-in-depth: resolve and ensure the target stays inside dist_dir
            file_path = (dist_dir / full_path).resolve()
            try:
                inside = file_path.is_relative_to(dist_dir.resolve())
            except AttributeError:  # py<3.9 fallback (not expected)
                inside = str(file_path).startswith(str(dist_dir.resolve()))
            if full_path and inside and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(dist_dir / "index.html")

    return app


app = create_app()


def main():
    """Run the QD2 server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "qd_server.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
