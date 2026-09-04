from fastapi import Depends, Request

from autometa.persistence.database import Database
from autometa.jobs.manager import JobManager
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.services.artifacts import ArtifactService
from autometa.services.reviews import ReviewService
from autometa.services.files import FileStorage


def get_database(request: Request) -> Database:
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise RuntimeError("AutoMeta database is not initialized")
    return database


def get_review_service(database: Database = Depends(get_database)) -> ReviewService:
    return ReviewService(ReviewRepository(database))


def get_file_storage(database: Database = Depends(get_database)) -> FileStorage:
    return FileStorage(database)


def get_artifact_service(database: Database = Depends(get_database)) -> ArtifactService:
    return ArtifactService(ArtifactRepository(database))


def get_job_manager(request: Request) -> JobManager:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:
        raise RuntimeError("AutoMeta job manager is not initialized")
    return manager
