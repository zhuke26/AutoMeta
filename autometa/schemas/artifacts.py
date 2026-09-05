from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from autometa.persistence.models import ArtifactState


class ArtifactDraftRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactApprovalRequest(BaseModel):
    artifact_id: str
    version: int = Field(ge=1)


class ArtifactView(BaseModel):
    artifact_id: str
    version_id: str
    review_id: str
    stage: str
    kind: str
    state: ArtifactState
    version: int
    payload: dict[str, Any]
    content_hash: str
    created_at: datetime
    approved: bool


class ArtifactVersionView(BaseModel):
    version_id: str
    artifact_id: str
    version: int
    payload: dict[str, Any]
    content_hash: str
    created_at: datetime
    approval_status: str | None
    approved_at: datetime | None
    revoked_at: datetime | None


class ArtifactDiffChange(BaseModel):
    op: Literal["add", "remove", "replace"]
    path: str
    before: Any | None = None
    after: Any | None = None


class ArtifactDiffView(BaseModel):
    artifact_id: str
    kind: str
    from_version: int
    to_version: int
    changes: list[ArtifactDiffChange] = Field(default_factory=list)
