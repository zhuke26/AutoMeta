from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autometa.persistence.database import Database
from autometa.persistence.models import (
    ProvenanceEdge,
    RerunRelationship,
    ResearcherEdit,
    ReviewEvent,
)


class ProvenanceRepository:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def next_sequence(session: Session, review_id: str) -> int:
        latest = session.scalar(
            select(func.max(ReviewEvent.sequence)).where(
                ReviewEvent.review_id == review_id
            )
        )
        return int(latest or 0) + 1

    @staticmethod
    def list_events(
        session: Session,
        review_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[ReviewEvent]:
        statement = (
            select(ReviewEvent)
            .where(
                ReviewEvent.review_id == review_id,
                ReviewEvent.sequence > after_sequence,
            )
            .order_by(ReviewEvent.sequence.asc())
            .limit(limit)
        )
        return list(session.scalars(statement))

    @staticmethod
    def event(session: Session, event_id: str) -> ReviewEvent | None:
        return session.get(ReviewEvent, event_id)

    @staticmethod
    def list_edges(session: Session, review_id: str) -> list[ProvenanceEdge]:
        return list(
            session.scalars(
                select(ProvenanceEdge)
                .where(ProvenanceEdge.review_id == review_id)
                .order_by(ProvenanceEdge.created_at.asc(), ProvenanceEdge.id.asc())
            )
        )

    @staticmethod
    def list_edits(session: Session, review_id: str) -> list[ResearcherEdit]:
        return list(
            session.scalars(
                select(ResearcherEdit)
                .where(ResearcherEdit.review_id == review_id)
                .order_by(ResearcherEdit.created_at.asc(), ResearcherEdit.id.asc())
            )
        )

    @staticmethod
    def list_reruns(session: Session, review_id: str) -> list[RerunRelationship]:
        return list(
            session.scalars(
                select(RerunRelationship)
                .where(RerunRelationship.review_id == review_id)
                .order_by(
                    RerunRelationship.created_at.asc(),
                    RerunRelationship.id.asc(),
                )
            )
        )

    @staticmethod
    def rerun_for_stage_run(
        session: Session,
        stage_run_id: str,
    ) -> RerunRelationship | None:
        return session.scalar(
            select(RerunRelationship).where(
                RerunRelationship.rerun_stage_run_id == stage_run_id
            )
        )
