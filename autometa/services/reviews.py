from __future__ import annotations

from autometa.persistence.models import Review, ReviewMode
from autometa.repositories.reviews import ReviewRepository


class ReviewNotFound(LookupError):
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
