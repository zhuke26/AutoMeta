from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from autometa.persistence.models import JobState


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    stage: str
    state: JobState
    progress: dict | None
    result_reference: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int = Field(ge=1)
    event_type: str
    payload: dict
    created_at: datetime


class StageRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    stage: str
    job_id: str | None
    status: str
    input_artifact_ids: list[str]
    operation_kind: str | None
    request_payload: dict
    input_artifact_version_ids: list[str]
    output_artifact_version_ids: list[str]
    created_at: datetime
    updated_at: datetime
