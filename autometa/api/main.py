"""
AutoMeta FastAPI application entry point.

Start with:
    uvicorn autometa.api.main:app --reload --port 8000

Pages:
    GET  /          → Web UI (autometa/static/index.html)
    GET  /docs      → Swagger UI

API:
    POST /api/v1/search  — PICO → candidate papers
    POST /api/v1/screen  — papers + PICO → inclusion decisions
    GET  /api/v1/health  — health check
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from autometa.api.routers import artifacts, extraction, files, jobs, meta_analysis, protocol, reviews, screening, search, system
from autometa.config import Settings, get_settings
from autometa.jobs.manager import JobManager
from autometa.persistence.database import Database
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.jobs import JobRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.services.artifacts import ArtifactService
from autometa.services.files import FileStorage
from autometa.services.reviews import ReviewService

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("autometa")
API_PREFIX = "/api/v1"

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    job_manager: JobManager | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_database = database or Database(resolved_settings)
        active_database.create_schema()
        active_database.mark_running_jobs_interrupted()
        active_manager = job_manager or JobManager(
            JobRepository(active_database),
            max_workers=resolved_settings.autometa_job_workers,
        )
        file_storage = FileStorage(active_database)
        application.state.database = active_database
        application.state.settings = resolved_settings
        application.state.job_manager = active_manager
        application.state.file_storage = file_storage
        application.state.artifact_service = ArtifactService(
            ArtifactRepository(active_database)
        )
        application.state.review_service = ReviewService(
            ReviewRepository(active_database),
            job_manager=active_manager,
        )
        try:
            yield
        finally:
            active_manager.shutdown()
            active_database.dispose()

    application = FastAPI(
        title="AutoMeta",
        description="Researcher-supervised evidence synthesis workspace API.",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(GZipMiddleware, minimum_size=500)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def cache_compiled_assets(request: Request, call_next):
        response = await call_next(request)
        if (
            request.url.path.startswith("/static/assets/")
            and response.status_code == status.HTTP_200_OK
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    application.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )

    @application.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(
            str(STATIC_DIR / "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    for router in (
        protocol.router,
        search.router,
        screening.router,
        extraction.router,
        meta_analysis.router,
        reviews.router,
        files.router,
        artifacts.router,
        jobs.router,
        system.router,
    ):
        application.include_router(router, prefix=API_PREFIX)

    @application.get(f"{API_PREFIX}/health", tags=["utility"])
    def health() -> dict[str, str]:
        return {"status": "ok", "product": "AutoMeta"}

    @application.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        reserved = ("api/", "static/", "docs", "redoc", "openapi.json")
        if full_path in reserved or full_path.startswith(reserved):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            str(STATIC_DIR / "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    return application


app = create_app()
