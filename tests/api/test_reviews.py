def test_create_list_open_and_rename_review(client) -> None:
    created = client.post(
        "/api/v1/reviews",
        json={"name": "Cardiac rehabilitation", "entry_mode": "guided"},
    )
    assert created.status_code == 201
    review_id = created.json()["id"]

    listing = client.get("/api/v1/reviews")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == review_id

    opened = client.get(f"/api/v1/reviews/{review_id}")
    assert opened.status_code == 200
    assert opened.json()["name"] == "Cardiac rehabilitation"

    renamed = client.patch(
        f"/api/v1/reviews/{review_id}", json={"name": "Updated review"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Updated review"


def test_review_name_cannot_be_blank(client) -> None:
    response = client.post(
        "/api/v1/reviews", json={"name": "   ", "entry_mode": "guided"}
    )
    assert response.status_code == 422


def test_unknown_review_returns_not_found(client) -> None:
    response = client.get("/api/v1/reviews/does-not-exist")
    assert response.status_code == 404


def test_reviews_are_ordered_by_most_recent_update(client) -> None:
    older = client.post(
        "/api/v1/reviews", json={"name": "Older", "entry_mode": "search"}
    ).json()
    newer = client.post(
        "/api/v1/reviews", json={"name": "Newer", "entry_mode": "extraction"}
    ).json()
    client.patch(f"/api/v1/reviews/{older['id']}", json={"name": "Updated older"})

    items = client.get("/api/v1/reviews").json()["items"]
    assert [item["id"] for item in items] == [older["id"], newer["id"]]
