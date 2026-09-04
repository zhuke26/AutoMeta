from fastapi import Depends, Request

from autometa.persistence.database import Database
from autometa.repositories.reviews import ReviewRepository
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
