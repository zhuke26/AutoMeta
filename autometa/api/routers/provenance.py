from fastapi import APIRouter, Depends, HTTPException

from autometa.api.dependencies import get_rerun_service
from autometa.schemas.jobs import JobView
from autometa.services.reruns import RerunConflict, RerunNotFound, RerunService

router = APIRouter(prefix="/reviews/{review_id}/provenance", tags=["provenance"])


@router.post("/events/{event_id}/rerun", response_model=JobView, status_code=202)
def rerun_event(
    review_id: str,
    event_id: str,
    service: RerunService = Depends(get_rerun_service),
) -> JobView:
    try:
        return service.rerun(review_id, event_id)
    except RerunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RerunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
