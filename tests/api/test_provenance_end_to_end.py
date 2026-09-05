from __future__ import annotations

import json
import time
from types import SimpleNamespace

from autometa.schemas.models import Paper, SearchTerms


def wait_for_terminal(client, job_id: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["state"] not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def test_correction_stale_rerun_and_audit_form_one_immutable_chain(
    client,
    monkeypatch,
) -> None:
    class FakeSearchAgent:
        calls = 0

        def search_with_raw_query(self, **_kwargs):
            self.__class__.calls += 1
            return SimpleNamespace(
                query_url="https://pubmed.example/search",
                total_count=1,
                retrieved_count=1,
                search_terms=SearchTerms(),
                papers=[Paper(
                    pmid=str(self.calls),
                    title=f"Search result {self.calls}",
                    abstract="",
                )],
            )

    monkeypatch.setattr(
        "autometa.services.workflow_operations.SearchAgent",
        FakeSearchAgent,
    )
    review = client.post(
        "/api/v1/reviews",
        json={"name": "Audit chain", "entry_mode": "guided"},
    ).json()
    review_id = review["id"]
    pico = client.put(
        f"/api/v1/reviews/{review_id}/artifacts/question_pico",
        json={"payload": {"pico": {"P": "Adults", "I": "Care", "C": "Usual", "O": "Recovery"}}},
    ).json()
    client.post(
        f"/api/v1/reviews/{review_id}/artifacts/question_pico/approve",
        json={"artifact_id": pico["artifact_id"], "version": pico["version"]},
    )
    query = client.put(
        f"/api/v1/reviews/{review_id}/artifacts/query",
        json={"payload": {"raw_query": "stroke[Title]"}},
    ).json()
    client.post(
        f"/api/v1/reviews/{review_id}/artifacts/query/approve",
        json={"artifact_id": query["artifact_id"], "version": query["version"]},
    )
    job = client.post(
        f"/api/v1/reviews/{review_id}/workflow/search/run",
        json={"retmax": 10, "fetch_all": False},
    ).json()
    assert wait_for_terminal(client, job["id"])["state"] == "succeeded"
    records = client.get(
        f"/api/v1/reviews/{review_id}/artifacts/records"
    ).json()
    client.post(
        f"/api/v1/reviews/{review_id}/artifacts/records/approve",
        json={"artifact_id": records["artifact_id"], "version": records["version"]},
    )

    client.put(
        f"/api/v1/reviews/{review_id}/artifacts/query",
        json={"payload": {"raw_query": "stroke[Title] AND trial[Title]"}},
    )
    assert client.get(
        f"/api/v1/reviews/{review_id}/artifacts/records"
    ).json()["state"] == "stale"

    events = client.get(f"/api/v1/reviews/{review_id}/provenance").json()
    source_event = next(
        event for event in events
        if event["event_type"] == "stage.completed" and event["stage"] == "search"
    )
    rerun_response = client.post(
        f"/api/v1/reviews/{review_id}/provenance/events/{source_event['id']}/rerun"
    )
    assert rerun_response.status_code == 202, rerun_response.json()
    rerun = rerun_response.json()
    assert wait_for_terminal(client, rerun["id"])["state"] == "succeeded"

    graph = client.get(f"/api/v1/reviews/{review_id}/provenance/graph").json()
    assert graph["edits"]
    assert graph["edges"]
    assert graph["reruns"]
    event_types = [event["event_type"] for event in graph["events"]]
    assert "artifact.stale" in event_types
    assert "rerun.started" in event_types
    assert "rerun.completed" in event_types

    audit = client.get(f"/api/v1/reviews/{review_id}/audit-export")
    assert audit.status_code == 200
    serialized = json.dumps(audit.json()).lower()
    assert "api_key" not in serialized
    assert "authorization" not in serialized
