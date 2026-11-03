"""Little List — FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .database import DEFAULT_DATABASE, initialize_database
from .routers import auth as auth_router
from .routers import stats as stats_router
from .routers import tasks as tasks_router

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(database_path: Path = DEFAULT_DATABASE) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(database_path)
        logger.info("Little List ready — database at %s", database_path)
        yield

    app = FastAPI(
        title="Little List API",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.state.database_path = database_path

    # --- routers ---
    app.include_router(tasks_router.router)
    app.include_router(auth_router.router)
    app.include_router(stats_router.router)

    # --- health check ---
    @app.get("/health", tags=["health"])
    def health():
        return {"status": "healthy"}

    # --- serve the SPA ---
    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(PROJECT_ROOT / "index.html")

    return app


app = create_app()
