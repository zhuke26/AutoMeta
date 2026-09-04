from sqlalchemy import select

from autometa.persistence.database import Database
from autometa.persistence.models import JobState, StageRun


class StageRunRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(
        self,
        review_id: str,
        stage: str,
        job_id: str,
        input_artifact_ids: list[str],
    ) -> StageRun:
        with self.database.session() as session:
            stage_run = StageRun(
                review_id=review_id,
                stage=stage,
                job_id=job_id,
                status=JobState.QUEUED.value,
                input_artifact_ids=list(input_artifact_ids),
            )
            session.add(stage_run)
            session.flush()
            return stage_run

    def get_by_job(self, job_id: str) -> StageRun | None:
        with self.database.session() as session:
            return session.scalar(select(StageRun).where(StageRun.job_id == job_id))

    def transition(self, job_id: str, state: JobState | str) -> StageRun:
        with self.database.session() as session:
            stage_run = session.scalar(
                select(StageRun).where(StageRun.job_id == job_id)
            )
            if stage_run is None:
                raise LookupError(job_id)
            stage_run.status = state.value if isinstance(state, JobState) else state
            session.flush()
            return stage_run
