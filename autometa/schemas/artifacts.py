from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from autometa.persistence.models import ArtifactState


class ArtifactDraftRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactApprovalRequest(BaseModel):
    artifact_id: str
    version: int = Field(ge=1)


class ArtifactView(BaseModel):
    artifact_id: str
    review_id: str
    stage: str
    kind: str
    state: ArtifactState
    version: int
    payload: dict[str, Any]
    content_hash: str
    created_at: datetime
    approved: bool
