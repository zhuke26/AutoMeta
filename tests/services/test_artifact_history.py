from __future__ import annotations

from sqlalchemy import select

from autometa.config import Settings
from autometa.persistence.database import Database
from autometa.persistence.models import ResearcherEdit, ReviewEvent, ReviewMode
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.services.artifacts import ArtifactService


def make_service(tmp_path):
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    review = ReviewRepository(database).create("History", ReviewMode.GUIDED)
    return database, review, ArtifactService(ArtifactRepository(database))


def test_versions_are_immutable_and_include_approval_history(tmp_path) -> None:
    database, review, service = make_service(tmp_path)
    first = service.save_draft(review.id, "query", {"raw_query": "A"})
    service.approve(review.id, first.artifact_id, first.version)
    second = service.save_draft(review.id, "query", {"raw_query": "A AND B"})

    versions = service.list_versions(review.id, "query")

    assert [item.version for item in versions] == [1, 2]
    assert versions[0].payload == {"raw_query": "A"}
    assert versions[0].approval_status == "revoked"
    assert versions[0].approved_at is not None
    assert versions[0].revoked_at is not None
    assert versions[1].version_id == second.version_id
    assert versions[1].approval_status is None
    database.dispose()


def test_researcher_edit_creates_deterministic_diff_and_event(tmp_path) -> None:
    database, review, service = make_service(tmp_path)
    service.save_draft(
        review.id,
        "query",
        {"filters": {"language": "English"}, "raw_query": "A", "terms": ["A"]},
    )
    service.save_draft(
        review.id,
        "query",
        {"filters": {}, "raw_query": "A AND B", "terms": ["A", "B"]},
    )

    diff = service.diff_versions(review.id, "query", 1, 2)

    assert [change.model_dump() for change in diff.changes] == [
        {
            "op": "remove",
            "path": "/filters/language",
            "before": "English",
            "after": None,
        },
        {
            "op": "replace",
            "path": "/raw_query",
            "before": "A",
            "after": "A AND B",
        },
        {
            "op": "replace",
            "path": "/terms",
            "before": ["A"],
            "after": ["A", "B"],
        },
    ]
    with database.session() as session:
        edit = session.scalar(select(ResearcherEdit))
        events = list(session.scalars(select(ReviewEvent).order_by(ReviewEvent.sequence)))
    assert edit is not None
    assert edit.changed_paths == ["/filters/language", "/raw_query", "/terms"]
    assert [event.event_type for event in events] == [
        "artifact.version_created",
        "artifact.version_created",
    ]
    database.dispose()


def test_approval_revoke_and_stale_transitions_are_recorded(tmp_path) -> None:
    database, review, service = make_service(tmp_path)
    query = service.save_draft(review.id, "query", {"raw_query": "A"})
    service.approve(review.id, query.artifact_id, query.version)
    records = service.save_draft(review.id, "records", {"papers": []})
    service.approve(review.id, records.artifact_id, records.version)

    service.save_draft(review.id, "query", {"raw_query": "A AND B"})

    with database.session() as session:
        events = list(session.scalars(select(ReviewEvent).order_by(ReviewEvent.sequence)))
    assert [event.event_type for event in events] == [
        "artifact.version_created",
        "artifact.approved",
        "artifact.version_created",
        "artifact.approved",
        "artifact.revoked",
        "artifact.revoked",
        "artifact.stale",
        "artifact.version_created",
    ]
    assert events[-2].payload == {"kind": "records", "upstream_kind": "query"}
    assert service.get_state(review.id, "records") == "stale"
    database.dispose()
