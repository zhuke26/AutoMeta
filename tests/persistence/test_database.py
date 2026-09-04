from autometa.config import Settings
from autometa.persistence.database import Database
from autometa.persistence.models import Base, Job, JobState, Review, ReviewMode


def test_database_creates_all_tables(tmp_path) -> None:
    settings = Settings(_env_file=None, autometa_data_dir=tmp_path)
    database = Database(settings)
    database.create_schema()

    assert set(Base.metadata.tables) <= set(database.inspect_table_names())


def test_startup_marks_queued_and_running_jobs_interrupted(tmp_path) -> None:
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    with database.session() as session:
        review = Review(name="Review", entry_mode=ReviewMode.GUIDED)
        session.add(review)
        session.flush()
        running = Job(review_id=review.id, stage="search", state=JobState.RUNNING)
        queued = Job(review_id=review.id, stage="screening", state=JobState.QUEUED)
        complete = Job(review_id=review.id, stage="extraction", state=JobState.SUCCEEDED)
        session.add_all([running, queued, complete])
        session.flush()
        job_ids = (running.id, queued.id, complete.id)

    assert database.mark_running_jobs_interrupted() == 2

    with database.session() as session:
        states = [session.get(Job, job_id).state for job_id in job_ids]

    assert states == [JobState.INTERRUPTED, JobState.INTERRUPTED, JobState.SUCCEEDED]
