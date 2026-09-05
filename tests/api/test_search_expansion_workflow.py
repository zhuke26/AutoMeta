import time

from autometa.schemas.models import (
    SearchExpansionResult,
    SearchQueryEvaluation,
    SearchQueryVariant,
    SearchStrategy,
    SearchStrategyComparison,
    SearchStrategySnapshot,
)


def wait_for_terminal(client, job_id: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["state"] not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def strategy(term: str) -> SearchStrategy:
    return SearchStrategy(
        topic_summary=term,
        field_tag_policy="Explicit",
        broad=SearchQueryVariant(name="broad", query=f"{term}[Title]", rationale="", expected_scope="broad"),
        balanced=SearchQueryVariant(name="balanced", query=f"{term}[Title/Abstract]", rationale="", expected_scope="balanced"),
        narrow=SearchQueryVariant(name="narrow", query=f"{term}[Title] AND trial[Title]", rationale="", expected_scope="narrow"),
    )


def evaluation(term: str, count: int) -> SearchQueryEvaluation:
    return SearchQueryEvaluation(
        name="balanced", total_count=count, retrieved_count=5,
        included_total=0, included_hits=0, included_recall=0,
        hit_pmids=[], missed_pmids=[], preview_pmids=[],
        query_url="https://pubmed.example", query=f"{term}[Title/Abstract]",
    )


def test_expansion_job_persists_reviewable_query_and_provenance(client, monkeypatch) -> None:
    class FakeSearchAgent:
        def expand_with_retrieval_feedback(self, *_args, **_kwargs):
            seed = strategy("stroke")
            expanded = strategy("rehabilitation")
            return SearchExpansionResult(
                seed=SearchStrategySnapshot(strategy=seed, evaluations=[evaluation("stroke", 100)]),
                expanded=SearchStrategySnapshot(strategy=expanded, evaluations=[evaluation("rehabilitation", 60)]),
                comparison=SearchStrategyComparison(
                    seed_query=seed.balanced.query,
                    expanded_query=expanded.balanced.query,
                    added_terms=["rehabilitation"],
                    removed_terms=["stroke"],
                    seed_result_count=100,
                    expanded_result_count=60,
                ),
            )

    monkeypatch.setattr("autometa.services.workflow_operations.SearchAgent", FakeSearchAgent)
    review = client.post("/api/v1/reviews", json={"name": "Expansion", "entry_mode": "guided"}).json()
    pico = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/question_pico",
        json={"payload": {"pico": {"P": "Adults", "I": "Therapy", "C": "Usual", "O": "Recovery"}}},
    ).json()
    client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/question_pico/approve",
        json={"artifact_id": pico["artifact_id"], "version": pico["version"]},
    )

    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/search/expand",
        json={"seed_retmax": 20, "included_pmids": [], "min_year": 2020, "max_year": 2025},
    )

    assert response.status_code == 202
    assert wait_for_terminal(client, response.json()["id"])["state"] == "succeeded"
    query = client.get(f"/api/v1/reviews/{review['id']}/artifacts/query").json()
    assert query["payload"]["raw_query"] == "rehabilitation[Title/Abstract]"
    assert query["payload"]["comparison"]["seed_result_count"] == 100
    events = client.get(f"/api/v1/reviews/{review['id']}/provenance").json()
    completed = next(item for item in events if item["event_type"] == "stage.completed")
    assert completed["payload"]["operation_kind"] == "search.expand"
    rerun = client.post(
        f"/api/v1/reviews/{review['id']}/provenance/events/{completed['id']}/rerun"
    )
    assert rerun.status_code == 202
    assert wait_for_terminal(client, rerun.json()["id"])["state"] == "succeeded"
    assert client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/query"
    ).json()["version"] == 2


def test_expansion_requires_approved_pico(client) -> None:
    review = client.post("/api/v1/reviews", json={"name": "Blocked", "entry_mode": "guided"}).json()
    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/search/expand",
        json={"seed_retmax": 20, "included_pmids": []},
    )
    assert response.status_code == 409
