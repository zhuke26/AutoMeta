from __future__ import annotations

import time
from types import SimpleNamespace

from autometa.persistence.models import JobState
from autometa.schemas.artifacts import ArtifactWriteContext
from autometa.schemas.models import Paper, SearchTerms
from autometa.schemas.provenance import Producer


def wait_for_terminal(client, job_id: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        if response.json()["state"] not in {"queued", "running"}:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def test_rerun_endpoint_starts_registered_historical_operation(client, monkeypatch) -> None:
    review = client.post(
        "/api/v1/reviews",
        json={"name": "Rerun API", "entry_mode": "guided"},
    ).json()
    artifacts = client.app.state.artifact_service
    jobs = client.app.state.job_manager.repository
    stage_runs = client.app.state.workflow_coordinator.stage_runs
    provenance = client.app.state.provenance_service

    pico = artifacts.save_draft(
        review["id"],
        "question_pico",
        {"pico": {"P": "Adults", "I": "Therapy", "C": "Usual care", "O": "Recovery"}},
    )
    approved_pico = artifacts.approve(review["id"], pico.artifact_id, pico.version)
    query = artifacts.save_draft(review["id"], "query", {"raw_query": "A"})
    approved = artifacts.approve(review["id"], query.artifact_id, query.version)
    source_job = jobs.create(review["id"], "search")
    jobs.transition(source_job.id, JobState.RUNNING)
    jobs.transition(source_job.id, JobState.SUCCEEDED)
    source_run = stage_runs.create(
        review["id"],
        "search",
        source_job.id,
        [approved_pico.artifact_id, approved.artifact_id],
        operation_kind="search.run",
        request_payload={"retmax": 10},
        input_artifact_version_ids=[approved_pico.version_id, approved.version_id],
    )
    source_run = stage_runs.transition(source_job.id, JobState.SUCCEEDED)
    output = artifacts.save_draft(
        review["id"],
        "records",
        {"papers": []},
        context=ArtifactWriteContext(
            producer=Producer.AGENT,
            stage_run_id=source_run.id,
            job_id=source_job.id,
            input_version_ids=(approved.version_id,),
        ),
    )
    event = provenance.record(
        review["id"],
        "stage.completed",
        Producer.SYSTEM,
        stage="search",
        stage_run_id=source_run.id,
        job_id=source_job.id,
        artifact_version_id=output.version_id,
    )

    class FakeSearchAgent:
        def search_with_raw_query(self, **_kwargs):
            return SimpleNamespace(
                query_url="https://pubmed.example/rerun",
                total_count=1,
                retrieved_count=1,
                search_terms=SearchTerms(),
                papers=[Paper(
                    pmid="2",
                    title="Rerun",
                    abstract="",
                )],
            )

    monkeypatch.setattr(
        "autometa.services.workflow_operations.SearchAgent",
        FakeSearchAgent,
    )
    response = client.post(
        f"/api/v1/reviews/{review['id']}/provenance/events/{event.id}/rerun"
    )

    assert response.status_code == 202
    terminal = wait_for_terminal(client, response.json()["id"])
    assert terminal["state"] == "succeeded"
    current_records = artifacts.get_current(review["id"], "records")
    assert current_records.version == 2
    assert current_records.payload["papers"][0]["title"] == "Rerun"


def test_rerun_endpoint_rejects_unknown_event(client) -> None:
    review = client.post(
        "/api/v1/reviews",
        json={"name": "Unknown rerun", "entry_mode": "guided"},
    ).json()

    response = client.post(
        f"/api/v1/reviews/{review['id']}/provenance/events/missing/rerun"
    )

    assert response.status_code == 404
