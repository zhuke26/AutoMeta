def create_review(client, name):
    return client.post(
        "/api/v1/reviews",
        json={"name": name, "entry_mode": "meta_analysis"},
    ).json()


def test_generated_figure_is_review_owned_and_downloadable(client) -> None:
    review = create_review(client, "Figures")
    other = create_review(client, "Other")
    record = client.app.state.file_storage.save_generated_figure(
        review["id"],
        "forest.svg",
        "image/svg+xml",
        b"<svg><text>Forest plot</text></svg>",
    )

    listing = client.get(f"/api/v1/reviews/{review['id']}/figures")
    content = client.get(
        f"/api/v1/reviews/{review['id']}/figures/{record.id}/content"
    )
    denied = client.get(
        f"/api/v1/reviews/{other['id']}/figures/{record.id}/content"
    )

    assert listing.status_code == 200
    assert listing.json()[0]["kind"] == "figure"
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/svg+xml")
    assert content.headers["content-disposition"] == 'inline; filename="forest.svg"'
    assert content.content.startswith(b"<svg")
    assert denied.status_code == 404


def test_generated_figure_is_removed_with_review(client) -> None:
    review = create_review(client, "Delete figures")
    record = client.app.state.file_storage.save_generated_figure(
        review["id"], "forest.png", "image/png", b"\x89PNG\r\n\x1a\nplot"
    )
    response = client.request(
        "DELETE",
        f"/api/v1/reviews/{review['id']}",
        json={"confirmation_name": review["name"]},
    )
    assert response.status_code == 204
    assert not client.app.state.file_storage.repository.get(record.id)
