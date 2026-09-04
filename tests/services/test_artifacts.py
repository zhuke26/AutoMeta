import pytest

from autometa.config import Settings
from autometa.persistence.database import Database
from autometa.persistence.models import ReviewMode
from autometa.repositories.artifacts import ArtifactRepository
from autometa.repositories.reviews import ReviewRepository
from autometa.services.artifacts import ArtifactConflict, ArtifactService


@pytest.fixture
def artifact_service(tmp_path):
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    service = ArtifactService(ArtifactRepository(database))
    yield database, service
    database.dispose()


@pytest.fixture
def review(artifact_service):
    database, _ = artifact_service
    return ReviewRepository(database).create("Artifact review", ReviewMode.GUIDED)


def test_only_approved_artifact_can_be_consumed(artifact_service, review) -> None:
    _, service = artifact_service
    draft = service.save_draft(review.id, "query", {"query": "sleep"})
    assert service.get_approved(review.id, "query") is None

    approved = service.approve(review.id, draft.artifact_id, draft.version)

    assert approved.state == "approved"
    assert service.get_approved(review.id, "query").payload == {"query": "sleep"}


def test_editing_approved_artifact_stales_downstream(artifact_service, review) -> None:
    _, service = artifact_service
    query = service.save_draft(review.id, "query", {"query": "sleep"})
    service.approve(review.id, query.artifact_id, query.version)
    records = service.save_draft(review.id, "records", {"count": 10})
    service.approve(review.id, records.artifact_id, records.version)

    revised = service.save_draft(
        review.id, "query", {"query": "sleep AND trial"}
    )

    assert revised.version == 2
    assert service.get_state(review.id, "query") == "draft"
    assert service.get_state(review.id, "records") == "stale"


def test_approve_rejects_noncurrent_version(artifact_service, review) -> None:
    _, service = artifact_service
    first = service.save_draft(review.id, "query", {"query": "sleep"})
    service.save_draft(review.id, "query", {"query": "sleep AND trial"})

    with pytest.raises(ArtifactConflict):
        service.approve(review.id, first.artifact_id, first.version)


def test_revoke_returns_artifact_to_draft(artifact_service, review) -> None:
    _, service = artifact_service
    draft = service.save_draft(review.id, "query", {"query": "sleep"})
    service.approve(review.id, draft.artifact_id, draft.version)

    revoked = service.revoke(review.id, "query")

    assert revoked.state == "draft"
    assert service.get_approved(review.id, "query") is None


def test_stale_artifact_cannot_be_reapproved_without_regeneration(
    artifact_service, review
) -> None:
    _, service = artifact_service
    query = service.save_draft(review.id, "query", {"query": "sleep"})
    service.approve(review.id, query.artifact_id, query.version)
    records = service.save_draft(review.id, "records", {"count": 10})
    service.approve(review.id, records.artifact_id, records.version)
    service.save_draft(review.id, "query", {"query": "sleep AND trial"})

    with pytest.raises(ArtifactConflict, match="stale"):
        service.approve(review.id, records.artifact_id, records.version)
