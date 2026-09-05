from fastapi import Request

from autometa.config import Settings
from autometa.jobs.manager import JobManager
from autometa.persistence.database import Database
from autometa.services.artifacts import ArtifactService
from autometa.services.files import FileStorage
from autometa.services.provenance import ProvenanceService
from autometa.services.reruns import RerunService
from autometa.services.reviews import ReviewService
from autometa.services.settings import LocalSettingsService
from autometa.services.workflow_operations import WorkflowOperationRegistry
from autometa.services.workflows import WorkflowCoordinator


def get_database(request: Request) -> Database:
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise RuntimeError("AutoMeta database is not initialized")
    return database


def get_review_service(request: Request) -> ReviewService:
    service = getattr(request.app.state, "review_service", None)
    if service is None:
        raise RuntimeError("AutoMeta Review service is not initialized")
    return service


def get_file_storage(request: Request) -> FileStorage:
    storage = getattr(request.app.state, "file_storage", None)
    if storage is None:
        raise RuntimeError("AutoMeta file storage is not initialized")
    return storage


def get_artifact_service(request: Request) -> ArtifactService:
    service = getattr(request.app.state, "artifact_service", None)
    if service is None:
        raise RuntimeError("AutoMeta artifact service is not initialized")
    return service


def get_job_manager(request: Request) -> JobManager:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:
        raise RuntimeError("AutoMeta job manager is not initialized")
    return manager


def get_workflow_coordinator(request: Request) -> WorkflowCoordinator:
    coordinator = getattr(request.app.state, "workflow_coordinator", None)
    if coordinator is None:
        raise RuntimeError("AutoMeta workflow coordinator is not initialized")
    return coordinator


def get_local_settings(request: Request) -> LocalSettingsService:
    service = getattr(request.app.state, "local_settings", None)
    if service is None:
        raise RuntimeError("AutoMeta local settings service is not initialized")
    return service


def get_provenance_service(request: Request) -> ProvenanceService:
    service = getattr(request.app.state, "provenance_service", None)
    if service is None:
        raise RuntimeError("AutoMeta provenance service is not initialized")
    return service


def get_rerun_service(request: Request) -> RerunService:
    service = getattr(request.app.state, "rerun_service", None)
    if service is None:
        raise RuntimeError("AutoMeta rerun service is not initialized")
    return service


def get_workflow_operations(request: Request) -> WorkflowOperationRegistry:
    registry = getattr(request.app.state, "workflow_operations", None)
    if registry is None:
        raise RuntimeError("AutoMeta workflow operation registry is not initialized")
    return registry


def get_app_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("AutoMeta settings are not initialized")
    return settings
