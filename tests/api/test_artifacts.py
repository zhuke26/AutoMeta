def _review(client):
    return client.post(
        "/api/v1/reviews",
        json={"name": "Artifact API", "entry_mode": "guided"},
    ).json()


def test_save_approve_and_list_artifact(client) -> None:
    review = _review(client)
    saved = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/query",
        json={"payload": {"query": "sleep"}},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["state"] == "draft"

    approved = client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/query/approve",
        json={"artifact_id": body["artifact_id"], "version": body["version"]},
    )
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"

    listing = client.get(f"/api/v1/reviews/{review['id']}/artifacts")
    assert listing.status_code == 200
    assert listing.json()[0]["kind"] == "query"


def test_unknown_artifact_kind_is_rejected(client) -> None:
    review = _review(client)
    response = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/not-real",
        json={"payload": {}},
    )
    assert response.status_code == 422


def test_noncurrent_approval_returns_conflict(client) -> None:
    review = _review(client)
    first = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/query",
        json={"payload": {"query": "first"}},
    ).json()
    client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/query",
        json={"payload": {"query": "second"}},
    )

    response = client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/query/approve",
        json={"artifact_id": first["artifact_id"], "version": first["version"]},
    )
    assert response.status_code == 409
