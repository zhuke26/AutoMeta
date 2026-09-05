from __future__ import annotations

from threading import RLock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from autometa.persistence.models import (
    Artifact,
    ArtifactVersion,
    Job,
    Review,
    ReviewEvent,
    StageRun,
)
from autometa.repositories.provenance import ProvenanceRepository
from autometa.schemas.provenance import (
    Producer,
    ProvenanceEdgeView,
    ProvenanceGraphView,
    RerunRelationshipView,
    ResearcherEditView,
    ReviewEventView,
)
from autometa.security import SecretRedactor


class ProvenanceNotFound(LookupError):
    pass


class ProvenanceConflict(RuntimeError):
    pass


class ProvenanceService:
    def __init__(self, repository: ProvenanceRepository):
        self.repository = repository
        self.redactor = SecretRedactor(repository.database.settings)
        self._sequence_lock = RLock()

    def safe_metadata(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        safe = self.redactor.payload(payload or {})
        if not isinstance(safe, dict):
            raise TypeError("Provenance metadata must be a dictionary")
        return safe

    def record(
        self,
        review_id: str,
        event_type: str,
        producer: Producer | str,
        *,
        stage: str | None = None,
        stage_run_id: str | None = None,
        job_id: str | None = None,
        artifact_version_id: str | None = None,
        elapsed_ms: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ReviewEventView:
        with self._sequence_lock, self.repository.database.session() as session:
            event = self.record_in_session(
                session,
                review_id,
                event_type,
                producer,
                stage=stage,
                stage_run_id=stage_run_id,
                job_id=job_id,
                artifact_version_id=artifact_version_id,
                elapsed_ms=elapsed_ms,
                payload=payload,
            )
            return ReviewEventView.model_validate(event)

    def record_in_session(
        self,
        session: Session,
        review_id: str,
        event_type: str,
        producer: Producer | str,
        *,
        stage: str | None = None,
        stage_run_id: str | None = None,
        job_id: str | None = None,
        artifact_version_id: str | None = None,
        elapsed_ms: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ReviewEvent:
        if session.get(Review, review_id) is None:
            raise ProvenanceNotFound(f"Review not found: {review_id}")
        self._validate_reference(session, StageRun, stage_run_id, review_id)
        self._validate_reference(session, Job, job_id, review_id)
        if artifact_version_id is not None:
            artifact_review_id = session.scalar(
                select(Artifact.review_id)
                .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
                .where(ArtifactVersion.id == artifact_version_id)
            )
            if artifact_review_id is None:
                raise ProvenanceNotFound(
                    f"Artifact version not found: {artifact_version_id}"
                )
            if artifact_review_id != review_id:
                raise ProvenanceConflict(
                    "Referenced records must belong to the same Review"
                )
        event = ReviewEvent(
            review_id=review_id,
            sequence=self.repository.next_sequence(session, review_id),
            stage=stage,
            event_type=event_type,
            producer=Producer(producer).value,
            stage_run_id=stage_run_id,
            job_id=job_id,
            artifact_version_id=artifact_version_id,
            elapsed_ms=elapsed_ms,
            payload=self.safe_metadata(payload),
        )
        session.add(event)
        session.flush()
        return event

    def list_events(
        self,
        review_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[ReviewEventView]:
        if after_sequence < 0:
            raise ValueError("after_sequence cannot be negative")
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        with self.repository.database.session() as session:
            if session.get(Review, review_id) is None:
                raise ProvenanceNotFound(f"Review not found: {review_id}")
            return [
                ReviewEventView.model_validate(event)
                for event in self.repository.list_events(
                    session,
                    review_id,
                    after_sequence=after_sequence,
                    limit=limit,
                )
            ]

    def graph(self, review_id: str) -> ProvenanceGraphView:
        with self.repository.database.session() as session:
            if session.get(Review, review_id) is None:
                raise ProvenanceNotFound(f"Review not found: {review_id}")
            return ProvenanceGraphView(
                events=[
                    ReviewEventView.model_validate(item)
                    for item in self.repository.list_events(session, review_id)
                ],
                edges=[
                    ProvenanceEdgeView.model_validate(item)
                    for item in self.repository.list_edges(session, review_id)
                ],
                edits=[
                    ResearcherEditView.model_validate(item)
                    for item in self.repository.list_edits(session, review_id)
                ],
                reruns=[
                    RerunRelationshipView.model_validate(item)
                    for item in self.repository.list_reruns(session, review_id)
                ],
            )

    @staticmethod
    def _validate_reference(
        session: Session,
        model: type[StageRun] | type[Job],
        record_id: str | None,
        review_id: str,
    ) -> None:
        if record_id is None:
            return
        record = session.get(model, record_id)
        if record is None:
            raise ProvenanceNotFound(f"Referenced record not found: {record_id}")
        if record.review_id != review_id:
            raise ProvenanceConflict("Referenced records must belong to the same Review")
