from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from autometa.config import Settings
from autometa.persistence.database import Database
from autometa.persistence.models import (
    Artifact,
    ArtifactVersion,
    Job,
    ProvenanceEdge,
    RerunRelationship,
    ResearcherEdit,
    Review,
    ReviewEvent,
    ReviewMode,
    StageRun,
)


def test_database_creates_provenance_tables_and_stage_run_columns(tmp_path) -> None:
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()

    assert {
        "review_events",
        "researcher_edits",
        "provenance_edges",
        "rerun_relationships",
    } <= set(database.inspect_table_names())
    assert {
        "operation_kind",
        "request_payload",
        "input_artifact_version_ids",
        "output_artifact_version_ids",
    } <= set(StageRun.__table__.columns.keys())

    database.dispose()


def test_review_event_sequence_is_unique_per_review(tmp_path) -> None:
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    with database.session() as session:
        review = Review(name="Provenance", entry_mode=ReviewMode.GUIDED)
        session.add(review)
        session.flush()
        review_id = review.id
        session.add(
            ReviewEvent(
                review_id=review_id,
                sequence=1,
                event_type="review.created",
                producer="system",
                payload={},
            )
        )

    with pytest.raises(IntegrityError):
        with database.session() as session:
            session.add(
                ReviewEvent(
                    review_id=review_id,
                    sequence=1,
                    event_type="duplicate",
                    producer="system",
                    payload={},
                )
            )

    database.dispose()


def test_review_delete_cascades_provenance_graph(tmp_path) -> None:
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    with database.session() as session:
        review = Review(name="Cascade", entry_mode=ReviewMode.GUIDED)
        session.add(review)
        session.flush()
        artifact = Artifact(review_id=review.id, stage="search", kind="query")
        source_job = Job(review_id=review.id, stage="search")
        rerun_job = Job(review_id=review.id, stage="search")
        session.add_all([artifact, source_job, rerun_job])
        session.flush()
        first = ArtifactVersion(
            artifact_id=artifact.id,
            version=1,
            payload={"raw_query": "A"},
            content_hash="a" * 64,
        )
        second = ArtifactVersion(
            artifact_id=artifact.id,
            version=2,
            payload={"raw_query": "A AND B"},
            content_hash="b" * 64,
        )
        source_run = StageRun(
            review_id=review.id,
            stage="search",
            job_id=source_job.id,
            status="succeeded",
            input_artifact_ids=[],
        )
        rerun = StageRun(
            review_id=review.id,
            stage="search",
            job_id=rerun_job.id,
            status="succeeded",
            input_artifact_ids=[],
        )
        session.add_all([first, second, source_run, rerun])
        session.flush()
        event = ReviewEvent(
            review_id=review.id,
            sequence=1,
            stage="search",
            event_type="stage.completed",
            producer="agent",
            stage_run_id=source_run.id,
            job_id=source_job.id,
            artifact_version_id=second.id,
            payload={},
        )
        session.add(event)
        session.flush()
        session.add_all([
            ResearcherEdit(
                review_id=review.id,
                artifact_id=artifact.id,
                from_version_id=first.id,
                to_version_id=second.id,
                changed_paths=["/raw_query"],
            ),
            ProvenanceEdge(
                review_id=review.id,
                source_version_id=first.id,
                target_version_id=second.id,
                relation="revised_to",
            ),
            RerunRelationship(
                review_id=review.id,
                source_stage_run_id=source_run.id,
                rerun_stage_run_id=rerun.id,
                source_event_id=event.id,
            ),
        ])
        session.delete(review)

    with database.session() as session:
        assert session.query(ReviewEvent).count() == 0
        assert session.query(ResearcherEdit).count() == 0
        assert session.query(ProvenanceEdge).count() == 0
        assert session.query(RerunRelationship).count() == 0

    database.dispose()
