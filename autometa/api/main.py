import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from autometa.api.routers import (
    artifacts,
    extraction,
    files,
    jobs,
    meta_analysis,
    protocol,
    provenance,
    reviews,
    screening,
    search,
    system,
    workflows,
)
from autometa.api.routers import settings as settings_router
from autometa.config import Settings, get_settings
from autometa.jobs.manager import JobManager
from autometa.persistence.database import Database
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.jobs import JobRepository
from autometa.repositories.provenance import ProvenanceRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.repositories.settings import LocalSettingsRepository
from autometa.repositories.stage_runs import StageRunRepository
from autometa.services.artifacts import ArtifactService
from autometa.services.audit_export import AuditExportService
from autometa.services.files import FileStorage
from autometa.services.provenance import ProvenanceService
from autometa.services.reruns import RerunService
from autometa.services.reviews import ReviewService
from autometa.services.settings import LocalSettingsService
from autometa.services.workflow_operations import WorkflowOperationRegistry
from autometa.services.workflows import WorkflowCoordinator

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
        local_settings = LocalSettingsService(LocalSettingsRepository(active_database))
        application.state.local_settings = local_settings
        provenance_service = ProvenanceService(ProvenanceRepository(active_database))
        artifact_service = ArtifactService(
            ArtifactRepository(active_database),
            provenance_service,
        )
        application.state.provenance_service = provenance_service
        application.state.audit_export_service = AuditExportService(
            active_database,
            provenance_service,
        )
        application.state.artifact_service = artifact_service
        workflow_coordinator = WorkflowCoordinator(
            active_manager,
            StageRunRepository(active_database),
            artifact_service,
            provenance_service,
        )
        workflow_operations = WorkflowOperationRegistry(
            artifacts=artifact_service,
            storage=file_storage,
            local_settings=local_settings,
        )
        application.state.workflow_coordinator = workflow_coordinator
        application.state.workflow_operations = workflow_operations
        application.state.rerun_service = RerunService(
            provenance=provenance_service,
            stage_runs=workflow_coordinator.stage_runs,
            artifacts=artifact_service,
            coordinator=workflow_coordinator,
            registry=workflow_operations,
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
        jobs.review_router,
        system.router,
        settings_router.router,
        workflows.router,
        provenance.router,
        provenance.audit_router,
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
