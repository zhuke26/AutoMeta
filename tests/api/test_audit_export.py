from __future__ import annotations

import json


def test_audit_export_is_portable_ordered_and_secret_free(client) -> None:
    review = client.post(
        "/api/v1/reviews",
        json={"name": "Audit", "entry_mode": "guided"},
    ).json()
    saved = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/query",
        json={"payload": {"raw_query": "A", "note": "safe"}},
    ).json()
    client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/query/approve",
        json={"artifact_id": saved["artifact_id"], "version": saved["version"]},
    )

    response = client.get(f"/api/v1/reviews/{review['id']}/audit-export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="autometa-review-{review["id"]}-audit.json"'
    )
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["review"]["id"] == review["id"]
    assert payload["artifacts"][0]["versions"][0]["payload"] == {
        "note": "safe",
        "raw_query": "A",
    }
    assert [event["sequence"] for event in payload["events"]] == [1, 2]
    serialized = json.dumps(payload).lower()
    assert "api_key" not in serialized
    assert "authorization" not in serialized
    assert str(client.app.state.database.data_dir).lower() not in serialized


def test_audit_export_rejects_unknown_review(client) -> None:
    response = client.get("/api/v1/reviews/missing/audit-export")
    assert response.status_code == 404
