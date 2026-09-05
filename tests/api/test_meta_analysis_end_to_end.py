import time

import pytest


def _wait_for_terminal(manager, job_id: str):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job.state not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def test_meta_analysis_result_figures_audit_and_review_cleanup(client) -> None:
    review = client.post(
        "/api/v1/reviews",
        json={"name": "Statistics end to end", "entry_mode": "meta_analysis"},
    ).json()
    review_id = review["id"]
    dataset = client.post(
        f"/api/v1/reviews/{review_id}/datasets",
        files={
            "files": (
                "effects.csv",
                b"study,effect,variance,group\n"
                b"Study A,0.20,0.04,Early\n"
                b"Study B,0.50,0.09,Early\n"
                b"Study C,0.10,0.01,Late\n"
                b"Study D,0.80,0.16,Late\n",
                "text/csv",
            )
        },
    ).json()[0]
    plan_payload = {
        "file_ids": [dataset["id"]],
        "plans": [{
            "csv_file": "effects.csv",
            "outcome_name": "Recovery",
            "method_text": "REML random-effects analysis",
            "analysis_type": "generic_effect",
            "effect_measure": "MD",
            "effect_source": "reported_effect_and_variance",
            "model": {
                "type": "random",
                "fixed_method": "inverse_variance",
                "random_method": "restricted_maximum_likelihood",
                "i2_threshold": 50,
            },
            "columns": {
                "study_label": "study",
                "effect": "effect",
                "variance": "variance",
            },
            "subgroup_column": "group",
            "output": {
                "include_study_effects": True,
                "include_weights": True,
                "include_pooled_effect": True,
                "include_heterogeneity": True,
                "include_output_csv": True,
                "include_prediction_interval": True,
                "include_leave_one_out": True,
                "include_subgroup": True,
                "include_forest_plot": True,
            },
        }],
    }
    plan = client.put(
        f"/api/v1/reviews/{review_id}/artifacts/plan",
        json={"payload": plan_payload},
    ).json()
    approved = client.post(
        f"/api/v1/reviews/{review_id}/artifacts/plan/approve",
        json={"artifact_id": plan["artifact_id"], "version": plan["version"]},
    )
    assert approved.status_code == 200

    response = client.post(
        f"/api/v1/reviews/{review_id}/workflow/meta/run",
        json={"confirm_strict_execution": True},
    )
    assert response.status_code == 202
    job = _wait_for_terminal(client.app.state.job_manager, response.json()["id"])
    assert job.state == "succeeded"

    result = client.get(
        f"/api/v1/reviews/{review_id}/artifacts/result"
    ).json()["payload"]["results"][0]
    assert result["pooled_effect"]["model_used"] == "random"
    assert result["heterogeneity"]["tau"] > 0
    assert result["prediction_interval"]["lower"] < result["pooled_effect"]["effect"]
    assert len(result["leave_one_out"]) == 4
    assert [group["label"] for group in result["subgroup_analysis"]["groups"]] == [
        "Early",
        "Late",
    ]
    assert result["subgroup_analysis"]["between_group_q"] == pytest.approx(
        0.0275507098,
        abs=2e-6,
    )
    figures = result["figure_files"]
    assert [figure["mime_type"] for figure in figures] == [
        "image/svg+xml",
        "image/png",
        "application/pdf",
    ]
    signatures = [b"<?xml", b"\x89PNG", b"%PDF"]
    for figure, signature in zip(figures, signatures):
        content = client.get(
            f"/api/v1/reviews/{review_id}/figures/{figure['file_id']}/content"
        )
        assert content.status_code == 200
        assert content.content.startswith(signature)

    audit = client.get(f"/api/v1/reviews/{review_id}/audit-export").json()
    figure_ids = [figure["file_id"] for figure in figures]
    assert [item["id"] for item in audit["files"] if item["kind"] == "figure"] == figure_ids
    assert audit["artifacts"][-1]["versions"][-1]["payload"]["results"][0][
        "figure_files"
    ] == figures

    review_directory = client.app.state.file_storage.review_directory(review_id)
    deleted = client.request(
        "DELETE",
        f"/api/v1/reviews/{review_id}",
        json={"confirmation_name": review["name"]},
    )
    assert deleted.status_code == 204
    assert not review_directory.exists()
    assert all(
        client.app.state.file_storage.repository.get(file_id) is None
        for file_id in figure_ids
    )
