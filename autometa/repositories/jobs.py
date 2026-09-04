from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from autometa.persistence.database import Database
from autometa.persistence.models import Job, JobEvent, JobState, Review, ReviewStatus


ACTIVE_JOB_STATES = (JobState.QUEUED, JobState.RUNNING)


class JobRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, review_id: str, stage: str) -> Job:
        with self.database.session() as session:
            review = session.get(Review, review_id)
            if review is None:
                raise LookupError(f"Review not found: {review_id}")
            if review.status is ReviewStatus.DELETING:
                raise RuntimeError("Review is being deleted")
            conflict = session.scalar(
                select(Job.id).where(
                    Job.review_id == review_id,
                    Job.stage == stage,
                    Job.state.in_(ACTIVE_JOB_STATES),
                )
            )
            if conflict is not None:
                raise RuntimeError("A job is already running for this stage")
            job = Job(review_id=review_id, stage=stage, state=JobState.QUEUED)
            session.add(job)
            session.flush()
            session.add(
                JobEvent(job_id=job.id, sequence=1, event_type="queued", payload={})
            )
            session.flush()
            return job

    def get(self, job_id: str) -> Job | None:
        with self.database.session() as session:
            return session.get(Job, job_id)

    def transition(
        self,
        job_id: str,
        state: JobState,
        *,
        payload: dict | None = None,
        result_reference: dict | None = None,
        error: str | None = None,
    ) -> Job:
        with self.database.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise LookupError(job_id)
            now = datetime.now(timezone.utc)
            job.state = state
            if state is JobState.RUNNING and job.started_at is None:
                job.started_at = now
            if state in {
                JobState.SUCCEEDED,
                JobState.FAILED,
                JobState.INTERRUPTED,
                JobState.CANCELLED,
            }:
                job.finished_at = now
            if payload is not None:
                job.progress = payload
            if result_reference is not None:
                job.result_reference = result_reference
            if error is not None:
                job.error = error
            self._append_event(session, job_id, state.value, payload or {})
            session.flush()
            return job

    def emit(self, job_id: str, event_type: str, payload: dict) -> JobEvent:
        with self.database.session() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise LookupError(job_id)
            job.progress = payload
            event = self._append_event(session, job_id, event_type, payload)
            session.flush()
            return event

    def events(self, job_id: str, after_sequence: int = 0) -> list[JobEvent]:
        with self.database.session() as session:
            statement = (
                select(JobEvent)
                .where(
                    JobEvent.job_id == job_id,
                    JobEvent.sequence > after_sequence,
                )
                .order_by(JobEvent.sequence.asc())
            )
            return list(session.scalars(statement))

    def active_for_review(self, review_id: str) -> list[Job]:
        with self.database.session() as session:
            statement = select(Job).where(
                Job.review_id == review_id,
                Job.state.in_(ACTIVE_JOB_STATES),
            )
            return list(session.scalars(statement))

    @staticmethod
    def _append_event(
        session,
        job_id: str,
        event_type: str,
        payload: dict,
    ) -> JobEvent:
        latest = session.scalar(
            select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id)
        )
        event = JobEvent(
            job_id=job_id,
            sequence=int(latest or 0) + 1,
            event_type=event_type,
            payload=payload,
        )
        session.add(event)
        return event
