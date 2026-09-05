import time
from pathlib import Path


def _create_review(client, name="Delete me"):
    return client.post(
        "/api/v1/reviews",
        json={"name": name, "entry_mode": "extraction"},
    ).json()


def test_upload_list_and_read_pdf(client) -> None:
    review = _create_review(client, "PDF review")
    uploaded = client.post(
        f"/api/v1/reviews/{review['id']}/files",
        files={"files": ("study.pdf", b"%PDF-1.7\nbody", "application/pdf")},
    )
    assert uploaded.status_code == 201
    file_record = uploaded.json()[0]

    listing = client.get(f"/api/v1/reviews/{review['id']}/files")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == file_record["id"]

    content = client.get(f"/api/v1/files/{file_record['id']}/content")
    assert content.status_code == 200
    assert content.content.startswith(b"%PDF-")


def test_wrong_confirmation_name_does_not_delete_review(client, database) -> None:
    review = _create_review(client)
    response = client.request(
        "DELETE",
        f"/api/v1/reviews/{review['id']}",
        json={"confirmation_name": "wrong"},
    )

    assert response.status_code == 409
    assert client.get(f"/api/v1/reviews/{review['id']}").status_code == 200


def test_exact_confirmation_deletes_database_and_files(client, database) -> None:
    review = _create_review(client)
    uploaded = client.post(
        f"/api/v1/reviews/{review['id']}/files",
        files={"files": ("study.pdf", b"%PDF-1.7\nbody", "application/pdf")},
    )
    assert uploaded.status_code == 201
    review_directory = Path(database.data_dir) / "reviews" / review["id"]
    assert review_directory.exists()

    response = client.request(
        "DELETE",
        f"/api/v1/reviews/{review['id']}",
        json={"confirmation_name": review["name"]},
    )

    assert response.status_code == 204
    assert client.get(f"/api/v1/reviews/{review['id']}").status_code == 404
    assert not review_directory.exists()


def test_delete_review_cancels_jobs_before_removing_files(client, database) -> None:
    review = _create_review(client, "Busy review")
    manager = client.app.state.job_manager

    def operation(context):
        while not context.cancelled:
            time.sleep(0.01)
        return {"cancelled": True}

    job = manager.submit(review["id"], "extraction", operation)
    deadline = time.monotonic() + 2
    while manager.get(job.id).state != "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    response = client.request(
        "DELETE",
        f"/api/v1/reviews/{review['id']}",
        json={"confirmation_name": review["name"]},
    )

    assert response.status_code == 204
    assert client.get(f"/api/v1/reviews/{review['id']}").status_code == 404
