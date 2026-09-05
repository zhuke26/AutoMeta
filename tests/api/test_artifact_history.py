def _review(client, name="History API"):
    return client.post(
        "/api/v1/reviews",
        json={"name": name, "entry_mode": "guided"},
    ).json()


def test_lists_versions_and_returns_a_deterministic_diff(client) -> None:
    review = _review(client)
    first = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/query",
        json={"payload": {"raw_query": "A"}},
    ).json()
    second = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/query",
        json={"payload": {"raw_query": "A AND B"}},
    ).json()

    versions = client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/query/versions"
    )
    diff = client.get(
        f"/api/v1/reviews/{review['id']}/artifacts/query/diff",
        params={"from_version": 1, "to_version": 2},
    )

    assert versions.status_code == 200
    assert [item["version_id"] for item in versions.json()] == [
        first["version_id"],
        second["version_id"],
    ]
    assert diff.status_code == 200
    assert diff.json()["changes"] == [{
        "op": "replace",
        "path": "/raw_query",
        "before": "A",
        "after": "A AND B",
    }]


def test_history_rejects_cross_review_access(client) -> None:
    first = _review(client, "First")
    second = _review(client, "Second")
    client.put(
        f"/api/v1/reviews/{first['id']}/artifacts/query",
        json={"payload": {"raw_query": "A"}},
    )

    response = client.get(
        f"/api/v1/reviews/{second['id']}/artifacts/query/versions/1"
    )

    assert response.status_code == 404
