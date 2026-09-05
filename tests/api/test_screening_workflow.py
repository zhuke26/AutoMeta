import time
from types import SimpleNamespace

PICO_PAYLOAD = {
    "research_question": "Does rehabilitation improve recovery after stroke?",
    "pico": {"P": "Adults", "I": "Rehabilitation", "C": "Usual care", "O": "Recovery"},
    "recommended_outcomes": [],
    "rationale": "",
}

PAPERS = [
    {
        "pmid": "100",
        "title": "Included trial",
        "abstract": "Relevant abstract",
        "authors": "Doe J",
        "year": "2024",
        "journal": "Journal A",
        "publication_type": "Randomized Controlled Trial",
    },
    {
        "pmid": "200",
        "title": "Uncertain study",
        "abstract": "Incomplete abstract",
        "authors": "Roe K",
        "year": "2023",
        "journal": "Journal B",
        "publication_type": "Clinical Trial",
    },
]


def _create_review(client):
    return client.post(
        "/api/v1/reviews",
        json={"name": "Screening workflow", "entry_mode": "screening"},
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


class SuccessfulScreeningAgent:
    def run_scored_direct(self, *, papers, pico, study_design_filter, max_concurrency):
        assert [paper.pmid for paper in papers] == ["100", "200"]
        assert pico.P == "Adults"
        assert study_design_filter.value == "rct_only"
        assert max_concurrency == 8
        return SimpleNamespace(model_dump=lambda: {
            "criteria": {},
            "decisions": [
                {
                    "pmid": "100",
                    "title": "Included trial",
                    "stage0_result": "KEEP",
                    "score_result": {
                        "scores": {"P": 1, "I": 1, "C": 0, "O": 1},
                        "confidence": {"P": 0.9, "I": 0.8, "C": 0.5, "O": 0.9},
                        "evidence": {"P": "Adults with stroke", "I": "Rehabilitation", "C": "Not reported", "O": "Recovery score"},
                        "weights": {"P": 1, "I": 1, "C": 1, "O": 1},
                        "weighted_score": 3,
                        "max_score": 4,
                        "threshold_rule": "Rank only",
                        "reasoning": "Relevant",
                    },
                    "final_decision": "INCLUDE",
                    "decision_stage": "ranking",
                },
                {
                    "pmid": "200",
                    "title": "Uncertain study",
                    "stage0_result": "KEEP",
                    "score_result": {
                        "scores": {"P": 1, "I": 0, "C": 0, "O": 0},
                        "confidence": {"P": 0.8, "I": 0.4, "C": 0.3, "O": 0.4},
                        "evidence": {"P": "Stroke", "I": "Unclear", "C": "Not reported", "O": "Unclear"},
                        "weights": {"P": 1, "I": 1, "C": 1, "O": 1},
                        "weighted_score": 1,
                        "max_score": 4,
                        "threshold_rule": "Rank only",
                        "reasoning": "Needs review",
                    },
                    "final_decision": "UNCERTAIN",
                    "decision_stage": "ranking",
                },
            ],
            "summary": {"total": 2, "final_included": 2, "final_excluded": 0},
            "screening_mode": "pico_ranking",
        })


def test_import_and_screening_job_persist_human_review_draft(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "autometa.api.routers.workflows.ScreeningAgentV2",
        SuccessfulScreeningAgent,
    )
    review = _create_review(client)
    pico = _save_and_approve(client, review["id"], "question_pico", PICO_PAYLOAD)
    imported = client.put(
        f"/api/v1/reviews/{review['id']}/workflow/screening/records",
        json={"papers": PAPERS, "source_format": "csv"},
    )
    assert imported.status_code == 200
    assert imported.json()["state"] == "draft"
    records = client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/records/approve",
        json={
            "artifact_id": imported.json()["artifact_id"],
            "version": imported.json()["version"],
        },
    ).json()

    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/screening/run",
        json={"study_design_filter": "rct_only", "max_concurrency": 8},
    )
    assert response.status_code == 202
    job = _wait_for_terminal(client.app.state.job_manager, response.json()["id"])
    assert job.state == "succeeded"
    selected = client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/selected_studies"
    ).json()
    assert selected["state"] == "draft"
    assert selected["payload"]["decisions"][0]["score_result"]["evidence"]["P"] == "Adults with stroke"
    assert selected["payload"]["selected_pmids"] == ["100", "200"]
    run = client.app.state.workflow_coordinator.stage_runs.get_by_job(job.id)
    assert run.input_artifact_ids == [pico["artifact_id"], records["artifact_id"]]


def test_screening_import_validates_rows_and_run_requires_approval(client) -> None:
    review = _create_review(client)
    invalid = client.put(
        f"/api/v1/reviews/{review['id']}/workflow/screening/records",
        json={"papers": [{"pmid": "", "title": ""}], "source_format": "json"},
    )
    assert invalid.status_code == 422

    _save_and_approve(client, review["id"], "question_pico", PICO_PAYLOAD)
    client.put(
        f"/api/v1/reviews/{review['id']}/workflow/screening/records",
        json={"papers": PAPERS, "source_format": "json"},
    )
    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/screening/run",
        json={},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Approve Records before starting this stage"
