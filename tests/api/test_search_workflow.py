import time

from autometa.schemas.models import (
    Paper,
    PICODefinition,
    SearchQueryVariant,
    SearchResult,
    SearchStrategy,
    SearchTerms,
)

PICO_PAYLOAD = {
    "research_question": "Does rehabilitation improve recovery after stroke?",
    "pico": {
        "P": "Adults after stroke",
        "I": "Structured rehabilitation",
        "C": "Usual care",
        "O": "Functional recovery",
    },
    "recommended_outcomes": [],
    "rationale": "",
}


def _create_review(client):
    return client.post(
        "/api/v1/reviews",
        json={"name": "Search workflow", "entry_mode": "guided"},
    ).json()


def _save_and_approve(client, review_id: str, kind: str, payload: dict):
    draft = client.put(
        f"/api/v1/reviews/{review_id}/artifacts/{kind}",
        json={"payload": payload},
    ).json()
    return client.post(
        f"/api/v1/reviews/{review_id}/artifacts/{kind}/approve",
        json={"artifact_id": draft["artifact_id"], "version": draft["version"]},
    ).json()


def _wait_for_terminal(manager, job_id: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.state not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


class SuccessfulSearchAgent:
    query = "stroke[Title/Abstract] AND rehabilitation[Title/Abstract]"

    def generate_field_tagged_strategy(self, pico: PICODefinition) -> SearchStrategy:
        assert pico.P == "Adults after stroke"
        return SearchStrategy(
            topic_summary="Stroke rehabilitation",
            field_tag_policy="Title and abstract fields",
            broad=SearchQueryVariant(name="broad", query="stroke", rationale="", expected_scope="Broad"),
            balanced=SearchQueryVariant(name="balanced", query=self.query, rationale="Balanced", expected_scope="Focused"),
            narrow=SearchQueryVariant(name="narrow", query="stroke[Title]", rationale="", expected_scope="Narrow"),
            warnings=[],
        )

    def search_with_raw_query(self, **kwargs) -> SearchResult:
        assert kwargs == {
            "raw_query": self.query,
            "retmax": 25,
            "min_year": 2018,
            "max_year": 2025,
            "fetch_all": False,
        }
        return SearchResult(
            query_url="https://pubmed.ncbi.nlm.nih.gov/?term=stroke",
            total_count=1,
            retrieved_count=1,
            search_terms=SearchTerms(
                populations=["stroke"],
                interventions=["rehabilitation"],
                outcomes=["recovery"],
            ),
            papers=[Paper(
                pmid="12345",
                title="Rehabilitation after stroke",
                abstract="A real abstract.",
                authors="Doe J",
                year="2024",
                journal="Journal",
                publication_type="Randomized Controlled Trial",
            )],
        )


def test_search_query_and_retrieval_jobs_persist_draft_artifacts(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "autometa.api.routers.workflows.SearchAgent",
        SuccessfulSearchAgent,
    )
    review = _create_review(client)
    pico = _save_and_approve(client, review["id"], "question_pico", PICO_PAYLOAD)

    query_response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/search/query",
        json={"strategy_mode": "field_tagged_balanced"},
    )
    assert query_response.status_code == 202
    query_job = _wait_for_terminal(
        client.app.state.job_manager,
        query_response.json()["id"],
    )
    assert query_job.state == "succeeded"
    query_artifact = client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/query"
    ).json()
    assert query_artifact["payload"]["generated_raw_query"] == SuccessfulSearchAgent.query
    assert query_artifact["payload"]["raw_query"] == SuccessfulSearchAgent.query
    assert query_artifact["state"] == "draft"

    approved_query = client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/query/approve",
        json={
            "artifact_id": query_artifact["artifact_id"],
            "version": query_artifact["version"],
        },
    ).json()
    run_response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/search/run",
        json={"retmax": 25, "fetch_all": False, "min_year": 2018, "max_year": 2025},
    )
    assert run_response.status_code == 202
    run_job = _wait_for_terminal(client.app.state.job_manager, run_response.json()["id"])
    assert run_job.state == "succeeded"
    records = client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/records"
    ).json()
    assert records["state"] == "draft"
    assert records["payload"]["papers"][0]["pmid"] == "12345"
    assert records["payload"]["retrieved_count"] == 1

    stage_run = client.app.state.workflow_coordinator.stage_runs.get_by_job(run_job.id)
    assert stage_run.input_artifact_ids == [pico["artifact_id"], approved_query["artifact_id"]]


def test_search_workflow_requires_approved_inputs(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "autometa.api.routers.workflows.SearchAgent",
        SuccessfulSearchAgent,
    )
    review = _create_review(client)
    client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/question_pico",
        json={"payload": PICO_PAYLOAD},
    )

    query = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/search/query",
        json={},
    )
    assert query.status_code == 409
    assert query.json()["detail"] == "Approve Question Pico before starting this stage"

    _save_and_approve(client, review["id"], "question_pico", PICO_PAYLOAD)
    run = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/search/run",
        json={},
    )
    assert run.status_code == 409
    assert run.json()["detail"] == "Approve Query before starting this stage"


def test_empty_generated_query_fails_job_without_records(client, monkeypatch) -> None:
    class EmptySearchAgent(SuccessfulSearchAgent):
        def generate_field_tagged_strategy(self, pico: PICODefinition) -> SearchStrategy:
            strategy = super().generate_field_tagged_strategy(pico)
            return strategy.model_copy(update={
                "balanced": strategy.balanced.model_copy(update={"query": "   "}),
            })

    monkeypatch.setattr(
        "autometa.api.routers.workflows.SearchAgent",
        EmptySearchAgent,
    )
    review = _create_review(client)
    _save_and_approve(client, review["id"], "question_pico", PICO_PAYLOAD)

    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/search/query",
        json={},
    )
    job = _wait_for_terminal(client.app.state.job_manager, response.json()["id"])

    assert job.state == "failed"
    assert job.error == "Generated PubMed query is empty"
    assert client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/query"
    ).status_code == 404
