ARTIFACT_KINDS = (
    "question_pico",
    "query",
    "records",
    "selected_studies",
    "sources",
    "plan",
    "code",
    "result",
)


def test_editing_approved_pico_invalidates_entire_guided_review_chain(client) -> None:
    review = client.post(
        "/api/v1/reviews",
        json={"name": "Guided flow", "entry_mode": "guided"},
    ).json()

    for kind in ARTIFACT_KINDS:
        draft = client.put(
            f"/api/v1/reviews/{review['id']}/artifacts/{kind}",
            json={"payload": {"kind": kind, "revision": 1}},
        ).json()
        approved = client.post(
            f"/api/v1/reviews/{review['id']}/artifacts/{kind}/approve",
            json={"artifact_id": draft["artifact_id"], "version": draft["version"]},
        )
        assert approved.status_code == 200

    revised = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/question_pico",
        json={"payload": {"kind": "question_pico", "revision": 2}},
    )
    assert revised.status_code == 200

    artifacts = {
        item["kind"]: item
        for item in client.get(
            f"/api/v1/reviews/{review['id']}/artifacts"
        ).json()
    }
    assert artifacts["question_pico"]["state"] == "draft"
    assert artifacts["question_pico"]["approved"] is False
    for kind in ARTIFACT_KINDS[1:]:
        assert artifacts[kind]["state"] == "stale"
        assert artifacts[kind]["approved"] is False

    blocked_search = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/search/query",
        json={},
    )
    blocked_meta = client.post(
        f"/api/v1/reviews/{review['id']}/workflow/meta/run",
        json={"confirm_strict_execution": True},
    )
    assert blocked_search.status_code == 409
    assert blocked_meta.status_code == 409
