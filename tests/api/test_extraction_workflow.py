import time

from autometa.schemas.extraction_models import (
    CharacteristicsRow,
    ExtractionOutput,
    FieldExtraction,
    ResultsRow,
)

PICO_PAYLOAD = {
    "research_question": "Does rehabilitation improve recovery after stroke?",
    "pico": {"P": "Adults", "I": "Rehabilitation", "C": "Usual care", "O": "Recovery"},
    "recommended_outcomes": [],
    "rationale": "",
}


def _create_review(client, name="Extraction workflow"):
    return client.post(
        "/api/v1/reviews",
        json={"name": name, "entry_mode": "extraction"},
    ).json()


def _approve_pico(client, review_id: str):
    draft = client.put(
        f"/api/v1/reviews/{review_id}/artifacts/question_pico",
        json={"payload": PICO_PAYLOAD},
    ).json()
    return client.post(
        f"/api/v1/reviews/{review_id}/artifacts/question_pico/approve",
        json={"artifact_id": draft["artifact_id"], "version": draft["version"]},
    ).json()


def _upload_pdf(client, review_id: str):
    return client.post(
        f"/api/v1/reviews/{review_id}/files",
        files={"files": ("study.pdf", b"%PDF-1.4\nlocal test", "application/pdf")},
    ).json()[0]


def _wait_for_terminal(manager, job_id: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.state not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


class SuccessfulExtractionAgent:
    def run(self, *, file_paths, pico, char_fields, result_fields, top_k, max_concurrency):
        assert len(file_paths) == 1
        assert file_paths[0].endswith(".pdf")
        assert pico.P == "Adults"
        assert [field.name for field in char_fields] == ["Sample size"]
        assert [field.name for field in result_fields] == ["Mean difference"]
        assert top_k == 12
        assert max_concurrency == 4
        return ExtractionOutput(
            characteristics=[CharacteristicsRow(
                filename="study.pdf",
                extractions=[FieldExtraction(
                    field_name="Sample size",
                    value="120",
                    citation="We randomized 120 participants.",
                    confidence="HIGH",
                )],
            )],
            results=[ResultsRow(
                filename="study.pdf",
                outcome_label="Functional recovery",
                extractions=[FieldExtraction(
                    field_name="Mean difference",
                    value="2.4",
                    citation="The adjusted mean difference was 2.4 points.",
                    confidence="HIGH",
                )],
            )],
        )


def test_pdf_disclosure_is_local_and_required(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "autometa.api.routers.workflows.ExtractionAgent",
        SuccessfulExtractionAgent,
    )
    review = _create_review(client)
    _approve_pico(client, review["id"])
    uploaded = _upload_pdf(client, review["id"])

    initial = client.get("/api/v1/settings/pdf-disclosure")
    assert initial.status_code == 200
    assert initial.json() == {"acknowledged": False}

    blocked = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/extraction/run",
        json={
            "file_ids": [uploaded["id"]],
            "study_characteristics_fields": [{"name": "Sample size"}],
            "study_results_fields": [],
        },
    )
    assert blocked.status_code == 409
    assert "PDF text" in blocked.json()["detail"]

    acknowledged = client.put(
        "/api/v1/settings/pdf-disclosure",
        json={"acknowledged": True},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json() == {"acknowledged": True}
    assert client.get("/api/v1/settings/pdf-disclosure").json() == {
        "acknowledged": True
    }


def test_extraction_job_uses_review_pdf_without_selected_studies(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "autometa.api.routers.workflows.ExtractionAgent",
        SuccessfulExtractionAgent,
    )
    review = _create_review(client)
    pico = _approve_pico(client, review["id"])
    uploaded = _upload_pdf(client, review["id"])
    client.put(
        "/api/v1/settings/pdf-disclosure",
        json={"acknowledged": True},
    )

    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/extraction/run",
        json={
            "file_ids": [uploaded["id"]],
            "study_characteristics_fields": [{"name": "Sample size"}],
            "study_results_fields": [{"name": "Mean difference"}],
            "top_k": 12,
            "max_concurrency": 4,
        },
    )
    assert response.status_code == 202
    job = _wait_for_terminal(client.app.state.job_manager, response.json()["id"])
    assert job.state == "succeeded"
    sources = client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/sources"
    ).json()
    assert sources["state"] == "draft"
    assert sources["payload"]["characteristics"][0]["extractions"][0]["citation"] == (
        "We randomized 120 participants."
    )
    assert sources["payload"]["results"][0]["extractions"][0]["value"] == "2.4"
    assert sources["payload"]["file_ids"] == [uploaded["id"]]
    run = client.app.state.workflow_coordinator.stage_runs.get_by_job(job.id)
    assert run.input_artifact_ids == [pico["artifact_id"]]


def test_extraction_rejects_file_from_another_review(client) -> None:
    review = _create_review(client)
    other = _create_review(client, "Other review")
    _approve_pico(client, review["id"])
    uploaded = _upload_pdf(client, other["id"])
    client.put(
        "/api/v1/settings/pdf-disclosure",
        json={"acknowledged": True},
    )

    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/extraction/run",
        json={
            "file_ids": [uploaded["id"]],
            "study_characteristics_fields": [{"name": "Sample size"}],
            "study_results_fields": [],
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "PDF does not belong to this Review"


def test_extraction_requires_at_least_one_field(client) -> None:
    review = _create_review(client)
    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/extraction/run",
        json={
            "file_ids": ["file-id"],
            "study_characteristics_fields": [],
            "study_results_fields": [],
        },
    )
    assert response.status_code == 422
