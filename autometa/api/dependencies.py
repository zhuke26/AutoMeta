from fastapi import Request

from autometa.persistence.database import Database
from autometa.jobs.manager import JobManager
from autometa.services.artifacts import ArtifactService
from autometa.services.reviews import ReviewService
from autometa.services.files import FileStorage


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
