"""QD Server main application entry point.

Creates and configures the FastAPI application with all routes,
middleware, and database initialization.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qd_server.api import api_router
from qd_server.config import get_settings

logger = logging.getLogger("qd2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    settings = get_settings()
    settings.ensure_config_dir()

    # Initialize database tables
    from sqlmodel import SQLModel

    async with settings.db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

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
    settings = get_settings()

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
            file_path = dist_dir / full_path
            if full_path and file_path.is_file():
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
