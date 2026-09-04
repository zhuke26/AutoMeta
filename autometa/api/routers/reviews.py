from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from autometa.api.dependencies import get_review_service
from autometa.schemas.reviews import ReviewCreate, ReviewList, ReviewSummary, ReviewUpdate
from autometa.services.reviews import ReviewNotFound, ReviewService


router = APIRouter(prefix="/reviews", tags=["reviews"])


def _not_found(review_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Review not found: {review_id}",
    )


@router.post("", response_model=ReviewSummary, status_code=status.HTTP_201_CREATED)
def create_review(
    request: ReviewCreate,
    service: ReviewService = Depends(get_review_service),
) -> ReviewSummary:
    return ReviewSummary.model_validate(service.create(request.name, request.entry_mode))


@router.get("", response_model=ReviewList)
def list_reviews(
    query: str | None = Query(default=None, max_length=160),
    service: ReviewService = Depends(get_review_service),
) -> ReviewList:
    items = [ReviewSummary.model_validate(item) for item in service.list(query)]
    return ReviewList(items=items, total=len(items))


@router.get("/{review_id}", response_model=ReviewSummary)
def get_review(
    review_id: str,
    service: ReviewService = Depends(get_review_service),
) -> ReviewSummary:
    try:
        return ReviewSummary.model_validate(service.get(review_id))
    except ReviewNotFound as exc:
        raise _not_found(review_id) from exc


@router.patch("/{review_id}", response_model=ReviewSummary)
def rename_review(
    review_id: str,
    request: ReviewUpdate,
    service: ReviewService = Depends(get_review_service),
) -> ReviewSummary:
    try:
        return ReviewSummary.model_validate(service.rename(review_id, request.name))
    except ReviewNotFound as exc:
        raise _not_found(review_id) from exc
