import threading
import time

from autometa.agents.protocol_agent import ProtocolDraft, RecommendedOutcome
from autometa.schemas.models import PICODefinition


def _create_review(client):
    return client.post(
        "/api/v1/reviews",
        json={"name": "Protocol workflow", "entry_mode": "guided"},
    ).json()


def _wait_for_terminal(manager, job_id: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.state not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


class SuccessfulProtocolAgent:
    def run(self, research_question: str) -> ProtocolDraft:
        assert research_question == "Does rehabilitation improve recovery after stroke?"
        return ProtocolDraft(
            pico=PICODefinition(
                P="Adults after stroke",
                I="Structured rehabilitation",
                C="Usual care",
                O="Functional recovery",
            ),
            recommended_outcomes=[
                RecommendedOutcome(
                    name="Functional independence",
                    type="primary",
                    rationale="Patient-important outcome",
                )
            ],
            rationale="Structured from the research question.",
        )


def test_protocol_job_persists_a_reviewable_draft_without_sse(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "autometa.api.routers.workflows.ProtocolAgent",
        SuccessfulProtocolAgent,
    )
    review = _create_review(client)

    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/protocol/draft",
        json={"research_question": "  Does rehabilitation improve recovery after stroke?  "},
    )

    assert response.status_code == 202
    job = _wait_for_terminal(client.app.state.job_manager, response.json()["id"])
    assert job.state == "succeeded"
    assert job.result_reference["kind"] == "question_pico"
    artifact = client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/question_pico"
    ).json()
    assert artifact["state"] == "draft"
    assert artifact["payload"]["research_question"] == (
        "Does rehabilitation improve recovery after stroke?"
    )
    assert artifact["payload"]["pico"]["P"] == "Adults after stroke"
    assert artifact["payload"]["recommended_outcomes"][0]["name"] == (
        "Functional independence"
    )
    assert [
        event.event_type
        for event in client.app.state.job_manager.events(job.id)
    ] == ["queued", "running", "drafting", "artifact_saved", "succeeded"]


def test_protocol_job_failure_is_persisted_without_creating_artifact(
    client,
    monkeypatch,
) -> None:
    class FailingProtocolAgent:
        def run(self, _research_question: str):
            raise RuntimeError("Configured provider rejected the request")

    monkeypatch.setattr(
        "autometa.api.routers.workflows.ProtocolAgent",
        FailingProtocolAgent,
    )
    review = _create_review(client)
    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/protocol/draft",
        json={"research_question": "Does rehabilitation improve recovery after stroke?"},
    )

    assert response.status_code == 202
    job = _wait_for_terminal(client.app.state.job_manager, response.json()["id"])
    assert job.state == "failed"
    assert job.error == "Configured provider rejected the request"
    assert client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/question_pico"
    ).status_code == 404


def test_protocol_workflow_rejects_missing_review_and_concurrent_run(
    client,
    monkeypatch,
) -> None:
    assert client.post(
        "/api/v1/reviews/missing/workflow/protocol/draft",
        json={"research_question": "Does rehabilitation improve recovery after stroke?"},
    ).status_code == 404

    started = threading.Event()
    release = threading.Event()

    class BlockingProtocolAgent:
        def run(self, _research_question: str):
            started.set()
            release.wait(timeout=2)
            return SuccessfulProtocolAgent().run(
                "Does rehabilitation improve recovery after stroke?"
            )

    monkeypatch.setattr(
        "autometa.api.routers.workflows.ProtocolAgent",
        BlockingProtocolAgent,
    )
    review = _create_review(client)
    first = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/protocol/draft",
        json={"research_question": "Does rehabilitation improve recovery after stroke?"},
    )
    assert first.status_code == 202
    assert started.wait(timeout=1)
    try:
        second = client.post(
            f"/api/v1/reviews/{review['id']}/workflow/protocol/draft",
            json={"research_question": "Does rehabilitation improve recovery after stroke?"},
        )
        assert second.status_code == 409
        assert second.json()["detail"] == "A job is already running for this stage"
    finally:
        release.set()
