import time
from types import SimpleNamespace

from autometa.schemas.meta_models import (
    EffectMeasure,
    EffectSource,
    MetaAnalysisColumns,
    MetaAnalysisMethodPlan,
    MetaAnalysisType,
    PoolingModelSpec,
)


PICO_PAYLOAD = {
    "research_question": "Does rehabilitation improve recovery after stroke?",
    "pico": {"P": "Adults", "I": "Rehabilitation", "C": "Usual care", "O": "Recovery"},
    "recommended_outcomes": [],
    "rationale": "",
}


def _create_review(client, name="Meta workflow"):
    return client.post(
        "/api/v1/reviews",
        json={"name": name, "entry_mode": "meta_analysis"},
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


def _upload_csv(client, review_id: str):
    content = b"study,mean_t,sd_t,n_t,mean_c,sd_c,n_c\nA,5,1,20,3,1,20\nB,6,2,30,4,2,30\n"
    return client.post(
        f"/api/v1/reviews/{review_id}/datasets",
        files={"files": ("effects.csv", content, "text/csv")},
    ).json()[0]


def _wait_for_terminal(manager, job_id: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.state not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def _method_plan():
    return MetaAnalysisMethodPlan(
        csv_file="effects.csv",
        outcome_name="Recovery score",
        method_text="Pool mean differences using a fixed inverse-variance model.",
        analysis_type=MetaAnalysisType.CONTINUOUS,
        effect_measure=EffectMeasure.MD,
        effect_source=EffectSource.ARM_LEVEL_DATA,
        model=PoolingModelSpec(type="fixed"),
        columns=MetaAnalysisColumns(
            study_label="study",
            experimental_mean="mean_t",
            experimental_sd="sd_t",
            experimental_total="n_t",
            control_mean="mean_c",
            control_sd="sd_c",
            control_total="n_c",
        ),
    )


class SuccessfulPlanner:
    def run(self, *, pico, csv_summaries, user_hint, max_concurrency):
        assert pico.O == "Recovery"
        assert csv_summaries[0].columns[0] == "study"
        assert csv_summaries[0].row_count == 2
        assert user_hint in {"", "Prefer mean difference"}
        assert max_concurrency == 1
        return SimpleNamespace(model_dump=lambda: {"plans": [_method_plan().model_dump(mode="json")]})


class SuccessfulRunner:
    def run(self, *, plans, csv_frames):
        assert plans[0].effect_measure == EffectMeasure.MD
        assert list(csv_frames) == ["effects.csv"]
        return SimpleNamespace(model_dump=lambda: {
            "results": [{
                "csv_file": "effects.csv",
                "outcome_name": "Recovery score",
                "study_effects": [{"study_label": "A", "effect": 2.0, "standard_error": 0.3, "ci_lower": 1.4, "ci_upper": 2.6, "weight_percent": 50.0}],
                "pooled_effect": {"model_used": "fixed", "effect_measure": "MD", "effect": 2.0, "standard_error": 0.2, "ci_lower": 1.6, "ci_upper": 2.4, "z_value": 10.0, "p_value": 0.001},
                "heterogeneity": {"q": 1.0, "df": 1, "p_value": 0.3, "i2_percent": 0.0, "tau2": 0.0},
                "output_csv": "study,effect\nA,2.0\n",
                "logs": ["Validated 2 studies"],
                "warnings": [],
            }],
            "generated_code": {"effects.csv": "print('validated')"},
        })


def test_dataset_upload_plan_approval_and_strict_run(client, monkeypatch) -> None:
    monkeypatch.setattr("autometa.api.routers.workflows.MetaAnalysisPlannerAgent", SuccessfulPlanner)
    monkeypatch.setattr("autometa.api.routers.workflows.MetaAnalysisRunnerAgent", SuccessfulRunner)
    review = _create_review(client)
    pico = _approve_pico(client, review["id"])
    dataset = _upload_csv(client, review["id"])
    assert dataset["kind"] == "csv"
    assert client.get(f"/api/v1/reviews/{review['id']}/datasets").json()[0]["id"] == dataset["id"]

    planned = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/meta/plan",
        json={"file_ids": [dataset["id"]], "user_hint": "Prefer mean difference"},
    )
    assert planned.status_code == 202
    plan_job = _wait_for_terminal(client.app.state.job_manager, planned.json()["id"])
    assert plan_job.state == "succeeded"
    plan = client.get(f"/api/v1/reviews/{review['id']}/artifacts/plan").json()
    assert plan["payload"]["plans"][0]["effect_measure"] == "MD"
    assert plan["payload"]["file_ids"] == [dataset["id"]]

    client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/plan/approve",
        json={"artifact_id": plan["artifact_id"], "version": plan["version"]},
    )
    run_response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/meta/run",
        json={"confirm_strict_execution": True},
    )
    assert run_response.status_code == 202
    run_job = _wait_for_terminal(client.app.state.job_manager, run_response.json()["id"])
    assert run_job.state == "succeeded"
    code = client.get(f"/api/v1/reviews/{review['id']}/artifacts/code").json()
    result = client.get(f"/api/v1/reviews/{review['id']}/artifacts/result").json()
    assert code["payload"]["generated_code"]["effects.csv"] == "print('validated')"
    assert result["payload"]["results"][0]["pooled_effect"]["effect"] == 2.0
    stage_run = client.app.state.workflow_coordinator.stage_runs.get_by_job(run_job.id)
    assert stage_run.input_artifact_ids == [plan["artifact_id"]]
    assert pico["artifact_id"] not in stage_run.input_artifact_ids


def test_meta_plan_rejects_foreign_dataset_and_run_requires_approved_plan(client) -> None:
    review = _create_review(client)
    other = _create_review(client, "Other")
    _approve_pico(client, review["id"])
    foreign = _upload_csv(client, other["id"])

    rejected = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/meta/plan",
        json={"file_ids": [foreign["id"]]},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "Dataset does not belong to this Review"

    missing_plan = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/meta/run",
        json={"confirm_strict_execution": True},
    )
    assert missing_plan.status_code == 409
    assert missing_plan.json()["detail"] == "Approve Plan before starting this stage"


def test_meta_runner_failure_does_not_create_code_or_result(client, monkeypatch) -> None:
    class FailingRunner:
        def run(self, *, plans, csv_frames):
            raise ValueError("Unsupported estimator; analysis stopped")

    monkeypatch.setattr("autometa.api.routers.workflows.MetaAnalysisPlannerAgent", SuccessfulPlanner)
    monkeypatch.setattr("autometa.api.routers.workflows.MetaAnalysisRunnerAgent", FailingRunner)
    review = _create_review(client)
    _approve_pico(client, review["id"])
    dataset = _upload_csv(client, review["id"])
    planned = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/meta/plan",
        json={"file_ids": [dataset["id"]]},
    ).json()
    _wait_for_terminal(client.app.state.job_manager, planned["id"])
    plan = client.get(f"/api/v1/reviews/{review['id']}/artifacts/plan").json()
    client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/plan/approve",
        json={"artifact_id": plan["artifact_id"], "version": plan["version"]},
    )

    response = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/meta/run",
        json={"confirm_strict_execution": True},
    )
    job = _wait_for_terminal(client.app.state.job_manager, response.json()["id"])
    assert job.state == "failed"
    assert job.error == "Unsupported estimator; analysis stopped"
    assert client.get(f"/api/v1/reviews/{review['id']}/artifacts/code").status_code == 404
    assert client.get(f"/api/v1/reviews/{review['id']}/artifacts/result").status_code == 404
