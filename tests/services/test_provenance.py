from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from autometa.config import Settings
from autometa.persistence.database import Database
from autometa.persistence.models import Job, ReviewMode
from autometa.repositories.provenance import ProvenanceRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.schemas.provenance import Producer
from autometa.services.provenance import ProvenanceConflict, ProvenanceService


@pytest.fixture
def provenance_setup(tmp_path):
    settings = Settings(
        _env_file=None,
        autometa_data_dir=tmp_path,
        llm_api_key="LLM_SENTINEL_SECRET",
        pubmed_api_key="PUBMED_SENTINEL_SECRET",
    )
    database = Database(settings)
    database.create_schema()
    reviews = ReviewRepository(database)
    first = reviews.create("First", ReviewMode.GUIDED)
    second = reviews.create("Second", ReviewMode.SEARCH)
    service = ProvenanceService(ProvenanceRepository(database))
    yield database, first, second, service
    database.dispose()


def test_records_monotonic_review_scoped_events(provenance_setup) -> None:
    _, first, second, service = provenance_setup
    service.record(first.id, "review.created", Producer.SYSTEM)
    service.record(first.id, "artifact.version_created", Producer.RESEARCHER)
    service.record(second.id, "review.created", Producer.SYSTEM)

    first_events = service.list_events(first.id)
    second_events = service.list_events(second.id)

    assert [event.sequence for event in first_events] == [1, 2]
    assert [event.event_type for event in first_events] == [
        "review.created",
        "artifact.version_created",
    ]
    assert [event.sequence for event in second_events] == [1]


def test_event_payload_recursively_redacts_credentials(provenance_setup) -> None:
    _, first, _, service = provenance_setup
    event = service.record(
        first.id,
        "stage.started",
        Producer.AGENT,
        payload={
            "api_key": "literal-value",
            "authorization": "Bearer literal-value",
            "nested": {
                "message": "LLM_SENTINEL_SECRET and PUBMED_SENTINEL_SECRET",
                "model": "test-model",
            },
        },
    )

    assert event.payload == {
        "api_key": "[REDACTED]",
        "authorization": "[REDACTED]",
        "nested": {
            "message": "[REDACTED] and [REDACTED]",
            "model": "test-model",
        },
    }


def test_rejects_cross_review_references(provenance_setup) -> None:
    database, first, second, service = provenance_setup
    with database.session() as session:
        job = Job(review_id=second.id, stage="search")
        session.add(job)
        session.flush()
        job_id = job.id

    with pytest.raises(ProvenanceConflict, match="same Review"):
        service.record(
            first.id,
            "stage.started",
            Producer.AGENT,
            job_id=job_id,
        )


def test_concurrent_events_keep_unique_contiguous_sequences(provenance_setup) -> None:
    _, first, _, service = provenance_setup

    def record(index: int) -> None:
        service.record(
            first.id,
            "progress",
            Producer.SYSTEM,
            payload={"index": index},
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(record, range(24)))

    assert [event.sequence for event in service.list_events(first.id, limit=30)] == list(
        range(1, 25)
    )


def test_event_pagination_is_stable(provenance_setup) -> None:
    _, first, _, service = provenance_setup
    for index in range(5):
        service.record(first.id, f"event.{index}", Producer.SYSTEM)

    page = service.list_events(first.id, after_sequence=2, limit=2)

    assert [event.sequence for event in page] == [3, 4]
