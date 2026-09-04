from __future__ import annotations

from autometa.persistence.models import Review, ReviewMode, ReviewStatus
from autometa.repositories.reviews import ReviewRepository
from autometa.services.files import FileStorage


class ReviewNotFound(LookupError):
    pass


class ReviewConfirmationMismatch(ValueError):
    pass


class ReviewService:
    def __init__(self, repository: ReviewRepository):
        self.repository = repository

    def create(self, name: str, entry_mode: ReviewMode) -> Review:
        return self.repository.create(name=name, entry_mode=entry_mode)

    def list(self, query: str | None = None) -> list[Review]:
        normalized = query.strip() if query else None
        return self.repository.list(normalized or None)

    def get(self, review_id: str) -> Review:
        review = self.repository.get(review_id)
        if review is None:
            raise ReviewNotFound(review_id)
        return review

    def rename(self, review_id: str, name: str) -> Review:
        review = self.repository.rename(review_id, name)
        if review is None:
            raise ReviewNotFound(review_id)
        return review

    def delete(
        self,
        review_id: str,
        confirmation_name: str,
        file_storage: FileStorage,
    ) -> None:
        review = self.get(review_id)
        if confirmation_name != review.name:
            raise ReviewConfirmationMismatch("Review name does not match")

        previous_status = review.status
        self.repository.set_status(review_id, ReviewStatus.DELETING)
        source, staged = file_storage.stage_review_directory(review_id)
        try:
            if not self.repository.delete(review_id):
                raise ReviewNotFound(review_id)
        except Exception:
            file_storage.restore_review_directory(source, staged)
            self.repository.set_status(review_id, previous_status)
            raise
        file_storage.purge_review_directory(staged)
