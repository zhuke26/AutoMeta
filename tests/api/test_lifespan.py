from fastapi.testclient import TestClient

from autometa.api.main import create_app
from autometa.config import Settings
from autometa.persistence.database import Database
from autometa.persistence.models import Job, JobState, Review, ReviewMode


def test_lifespan_initializes_database_and_services(tmp_path) -> None:
    test_app = create_app(Settings(_env_file=None, autometa_data_dir=tmp_path))

    with TestClient(test_app) as client:
        assert client.app.state.database.inspect_table_names()
        assert client.app.state.review_service is not None
        assert client.app.state.file_storage is not None
        assert client.app.state.artifact_service is not None
        manager = client.app.state.job_manager
        assert manager.closed is False

    assert manager.closed is True


def test_lifespan_marks_abandoned_jobs_interrupted(tmp_path) -> None:
    settings = Settings(_env_file=None, autometa_data_dir=tmp_path)
    database = Database(settings)
    database.create_schema()
    with database.session() as session:
        review = Review(name="Interrupted", entry_mode=ReviewMode.GUIDED)
        session.add(review)
        session.flush()
        job = Job(review_id=review.id, stage="search", state=JobState.RUNNING)
        session.add(job)
        session.flush()
        job_id = job.id
    database.dispose()

    test_app = create_app(settings)
    with TestClient(test_app):
        with test_app.state.database.session() as session:
            assert session.get(Job, job_id).state is JobState.INTERRUPTED
