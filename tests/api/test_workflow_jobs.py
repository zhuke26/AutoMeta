import time

from autometa.persistence.models import ReviewMode
from autometa.repositories.reviews import ReviewRepository


def _wait_for_terminal(manager, job_id: str) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if manager.get(job_id).state not in {"queued", "running"}:
            return
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {job_id}")


def test_review_jobs_are_newest_first_filtered_and_isolated(client, database) -> None:
    reviews = ReviewRepository(database)
    first_review = reviews.create("First", ReviewMode.GUIDED)
    second_review = reviews.create("Second", ReviewMode.SEARCH)
    manager = client.app.state.job_manager

    first = manager.submit(first_review.id, "search", lambda _context: {"value": 1})
    _wait_for_terminal(manager, first.id)
    second = manager.submit(first_review.id, "screening", lambda _context: {"value": 2})
    _wait_for_terminal(manager, second.id)
    foreign = manager.submit(second_review.id, "search", lambda _context: {"value": 3})
    _wait_for_terminal(manager, foreign.id)

    response = client.get(f"/api/v1/reviews/{first_review.id}/jobs")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [second.id, first.id]

    filtered = client.get(
        f"/api/v1/reviews/{first_review.id}/jobs",
        params={"stage": "search", "limit": 1},
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [first.id]
    assert foreign.id not in response.text


def test_review_jobs_returns_specific_not_found(client) -> None:
    response = client.get("/api/v1/reviews/missing/jobs")

    assert response.status_code == 404
    assert response.json() == {"detail": "Review not found: missing"}
