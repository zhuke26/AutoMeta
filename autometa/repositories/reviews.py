from __future__ import annotations

from sqlalchemy import select

from autometa.persistence.database import Database
from autometa.persistence.models import Review, ReviewMode, ReviewStatus


class ReviewRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, name: str, entry_mode: ReviewMode) -> Review:
        with self.database.session() as session:
            review = Review(name=name, entry_mode=entry_mode)
            session.add(review)
            session.flush()
            return review

    def list(self, query: str | None = None) -> list[Review]:
        with self.database.session() as session:
            statement = select(Review)
            if query:
                statement = statement.where(Review.name.ilike(f"%{query}%"))
            statement = statement.order_by(Review.updated_at.desc(), Review.created_at.desc())
            return list(session.scalars(statement))

    def get(self, review_id: str) -> Review | None:
        with self.database.session() as session:
            return session.get(Review, review_id)

    def rename(self, review_id: str, name: str) -> Review | None:
        with self.database.session() as session:
            review = session.get(Review, review_id)
            if review is None:
                return None
            review.name = name
            return review

    def set_status(self, review_id: str, status: ReviewStatus) -> Review | None:
        with self.database.session() as session:
            review = session.get(Review, review_id)
            if review is None:
                return None
            review.status = status
            return review

    def delete(self, review_id: str) -> bool:
        with self.database.session() as session:
            review = session.get(Review, review_id)
            if review is None:
                return False
            session.delete(review)
            return True
