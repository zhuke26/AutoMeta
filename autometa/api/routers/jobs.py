from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from autometa.api.dependencies import get_job_manager
from autometa.jobs.manager import JobManager, JobNotFound
from autometa.persistence.models import JobState
from autometa.schemas.jobs import JobView


router = APIRouter(prefix="/jobs", tags=["jobs"])
TERMINAL_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.INTERRUPTED,
    JobState.CANCELLED,
}


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
