from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from autometa.api.dependencies import get_job_manager, get_review_service
from autometa.jobs.manager import JobManager, JobNotFound
from autometa.persistence.models import JobState
from autometa.schemas.jobs import JobView
from autometa.services.reviews import ReviewNotFound, ReviewService

router = APIRouter(prefix="/jobs", tags=["jobs"])
review_router = APIRouter(prefix="/reviews/{review_id}/jobs", tags=["jobs"])
TERMINAL_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.INTERRUPTED,
    JobState.CANCELLED,
}


@review_router.get("", response_model=list[JobView])
def list_review_jobs(
    review_id: str,
    stage: str | None = Query(default=None, min_length=1, max_length=32),
    limit: int = Query(default=20, ge=1, le=100),
    manager: JobManager = Depends(get_job_manager),
    reviews: ReviewService = Depends(get_review_service),
) -> list[JobView]:
    try:
        reviews.get(review_id)
    except ReviewNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Review not found: {review_id}",
        ) from exc
    return manager.list_for_review(review_id, stage=stage, limit=limit)


@router.get("/{job_id}", response_model=JobView)
def get_job(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
) -> JobView:
    try:
        return manager.get(job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    manager: JobManager = Depends(get_job_manager),
) -> StreamingResponse:
    try:
        manager.get(job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc

    async def stream():
        sequence = after
        while True:
            events = manager.events(job_id, after_sequence=sequence)
            for event in events:
                sequence = event.sequence
                data = json.dumps(event.payload, ensure_ascii=False)
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {data}\n\n"
            job = manager.get(job_id)
            if job.state in TERMINAL_STATES and not events:
                break
            if await request.is_disconnected():
                break
            await asyncio.sleep(0.1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
