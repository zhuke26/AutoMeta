def create_review(client, name):
    return client.post(
        "/api/v1/reviews",
        json={"name": name, "entry_mode": "extraction"},
    ).json()


def upload_pdf(client, review_id):
    return client.post(
        f"/api/v1/reviews/{review_id}/files",
        files={"files": ("study.pdf", b"%PDF-1.4\nsource-linked-content", "application/pdf")},
    ).json()[0]


def test_review_owned_pdf_supports_inline_full_and_range_responses(client) -> None:
    review = create_review(client, "PDF")
    uploaded = upload_pdf(client, review["id"])
    url = f"/api/v1/reviews/{review['id']}/files/{uploaded['id']}/content"

    full = client.get(url)
    partial = client.get(url, headers={"Range": "bytes=0-7"})

    assert full.status_code == 200
    assert full.content.startswith(b"%PDF-1.4")
    assert full.headers["content-type"] == "application/pdf"
    assert full.headers["cache-control"] == "private, no-store"
    assert full.headers["content-disposition"].startswith("inline;")
    assert partial.status_code == 206
    assert partial.content == b"%PDF-1.4"
    assert partial.headers["content-range"].startswith("bytes 0-7/")


def test_pdf_content_enforces_review_ownership_and_pdf_kind(client) -> None:
    first = create_review(client, "First")
    second = create_review(client, "Second")
    uploaded = upload_pdf(client, first["id"])

    wrong_review = client.get(
        f"/api/v1/reviews/{second['id']}/files/{uploaded['id']}/content"
    )
    legacy_unscoped = client.get(f"/api/v1/files/{uploaded['id']}/content")

    assert wrong_review.status_code == 404
    assert legacy_unscoped.status_code == 404


def test_pdf_content_rejects_invalid_range(client) -> None:
    review = create_review(client, "Range")
    uploaded = upload_pdf(client, review["id"])
    response = client.get(
        f"/api/v1/reviews/{review['id']}/files/{uploaded['id']}/content",
        headers={"Range": "bytes=999-1000"},
    )
    assert response.status_code == 416
    assert "autometa" not in response.text.lower()
