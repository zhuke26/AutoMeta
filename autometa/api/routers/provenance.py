import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from autometa.api.dependencies import (
    get_audit_export_service,
    get_provenance_service,
    get_rerun_service,
)
from autometa.schemas.jobs import JobView
from autometa.schemas.provenance import ProvenanceGraphView, ReviewEventView
from autometa.services.audit_export import AuditExportService
from autometa.services.provenance import ProvenanceNotFound, ProvenanceService
from autometa.services.reruns import RerunConflict, RerunNotFound, RerunService

router = APIRouter(prefix="/reviews/{review_id}/provenance", tags=["provenance"])
audit_router = APIRouter(prefix="/reviews/{review_id}", tags=["provenance"])


@router.get("", response_model=list[ReviewEventView])
def list_events(
    review_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    service: ProvenanceService = Depends(get_provenance_service),
) -> list[ReviewEventView]:
    try:
        return service.list_events(
            review_id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except ProvenanceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/graph", response_model=ProvenanceGraphView)
def provenance_graph(
    review_id: str,
    service: ProvenanceService = Depends(get_provenance_service),
) -> ProvenanceGraphView:
    try:
        return service.graph(review_id)
    except ProvenanceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@audit_router.get("/audit-export")
def audit_export(
    review_id: str,
    service: AuditExportService = Depends(get_audit_export_service),
) -> StreamingResponse:
    try:
        payload = service.build(review_id)
    except ProvenanceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    body = json.dumps(
        jsonable_encoder(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return StreamingResponse(
        iter((body,)),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="autometa-review-{review_id}-audit.json"'
            )
        },
    )
