from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from autometa.api.dependencies import get_artifact_service
from autometa.schemas.artifacts import (
    ArtifactApprovalRequest,
    ArtifactDiffView,
    ArtifactDraftRequest,
    ArtifactVersionView,
    ArtifactView,
)
from autometa.services.artifacts import (
    ArtifactConflict,
    ArtifactNotFound,
    ArtifactService,
    InvalidArtifactKind,
)

router = APIRouter(prefix="/reviews/{review_id}/artifacts", tags=["artifacts"])


def _raise_for_error(exc: Exception) -> None:
    if isinstance(exc, InvalidArtifactKind):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, ArtifactConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[ArtifactView])
def list_artifacts(
    review_id: str,
    service: ArtifactService = Depends(get_artifact_service),
) -> list[ArtifactView]:
    try:
        return service.list(review_id)
    except (ArtifactNotFound, InvalidArtifactKind) as exc:
        _raise_for_error(exc)


@router.get("/{kind}", response_model=ArtifactView)
def get_artifact(
    review_id: str,
    kind: str,
    service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactView:
    try:
        return service.get_current(review_id, kind)
    except (ArtifactNotFound, InvalidArtifactKind) as exc:
        _raise_for_error(exc)


@router.get("/{kind}/versions", response_model=list[ArtifactVersionView])
def list_artifact_versions(
    review_id: str,
    kind: str,
    service: ArtifactService = Depends(get_artifact_service),
) -> list[ArtifactVersionView]:
    try:
        return service.list_versions(review_id, kind)
    except (ArtifactNotFound, InvalidArtifactKind) as exc:
        _raise_for_error(exc)


@router.get("/{kind}/versions/{version}", response_model=ArtifactVersionView)
def get_artifact_version(
    review_id: str,
    kind: str,
    version: int,
    service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactVersionView:
    try:
        return service.get_version(review_id, kind, version)
    except (ArtifactNotFound, InvalidArtifactKind) as exc:
        _raise_for_error(exc)


@router.get("/{kind}/diff", response_model=ArtifactDiffView)
def diff_artifact_versions(
    review_id: str,
    kind: str,
    from_version: int = Query(ge=1),
    to_version: int = Query(ge=1),
    service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactDiffView:
    try:
        return service.diff_versions(review_id, kind, from_version, to_version)
    except (ArtifactNotFound, InvalidArtifactKind) as exc:
        _raise_for_error(exc)


@router.put("/{kind}", response_model=ArtifactView)
def save_artifact(
    review_id: str,
    kind: str,
    request: ArtifactDraftRequest,
    service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactView:
    try:
        return service.save_draft(review_id, kind, request.payload)
    except (ArtifactNotFound, InvalidArtifactKind) as exc:
        _raise_for_error(exc)


@router.post("/{kind}/approve", response_model=ArtifactView)
def approve_artifact(
    review_id: str,
    kind: str,
    request: ArtifactApprovalRequest,
    service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactView:
    try:
        current = service.get_current(review_id, kind)
        if current.artifact_id != request.artifact_id:
            raise ArtifactConflict("Artifact identifier does not match")
        return service.approve(review_id, request.artifact_id, request.version)
    except (ArtifactNotFound, InvalidArtifactKind, ArtifactConflict) as exc:
        _raise_for_error(exc)


@router.post("/{kind}/revoke", response_model=ArtifactView)
def revoke_artifact(
    review_id: str,
    kind: str,
    service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactView:
    try:
        return service.revoke(review_id, kind)
    except (ArtifactNotFound, InvalidArtifactKind, ArtifactConflict) as exc:
        _raise_for_error(exc)
