def test_lists_review_events_and_graph_in_sequence_order(client) -> None:
    review = client.post(
        "/api/v1/reviews",
        json={"name": "Timeline", "entry_mode": "guided"},
    ).json()
    first = client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/query",
        json={"payload": {"raw_query": "A"}},
    ).json()
    client.post(
        f"/api/v1/reviews/{review['id']}/artifacts/query/approve",
        json={"artifact_id": first["artifact_id"], "version": first["version"]},
    )
    client.put(
        f"/api/v1/reviews/{review['id']}/artifacts/query",
        json={"payload": {"raw_query": "A AND B"}},
    )

    timeline = client.get(f"/api/v1/reviews/{review['id']}/provenance")
    graph = client.get(f"/api/v1/reviews/{review['id']}/provenance/graph")

    assert timeline.status_code == 200
    assert [event["sequence"] for event in timeline.json()] == [1, 2, 3, 4]
    assert [event["event_type"] for event in timeline.json()] == [
        "artifact.version_created",
        "artifact.approved",
        "artifact.revoked",
        "artifact.version_created",
    ]
    assert graph.status_code == 200
    assert [event["sequence"] for event in graph.json()["events"]] == [1, 2, 3, 4]
    assert len(graph.json()["edits"]) == 1


def test_provenance_api_is_review_scoped(client) -> None:
    first = client.post(
        "/api/v1/reviews",
        json={"name": "First", "entry_mode": "guided"},
    ).json()
    second = client.post(
        "/api/v1/reviews",
        json={"name": "Second", "entry_mode": "guided"},
    ).json()
    client.put(
        f"/api/v1/reviews/{first['id']}/artifacts/query",
        json={"payload": {"raw_query": "A"}},
    )

    assert client.get(f"/api/v1/reviews/{second['id']}/provenance").json() == []
    assert client.get("/api/v1/reviews/missing/provenance").status_code == 404
