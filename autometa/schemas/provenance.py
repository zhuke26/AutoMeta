from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Producer(StrEnum):
    RESEARCHER = "researcher"
    AGENT = "agent"
    SYSTEM = "system"


class ReviewEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    sequence: int = Field(ge=1)
    stage: str | None
    event_type: str
    producer: Producer
    stage_run_id: str | None
    job_id: str | None
    artifact_version_id: str | None
    elapsed_ms: int | None
    payload: dict[str, Any]
    created_at: datetime


class ResearcherEditView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    artifact_id: str
    from_version_id: str | None
    to_version_id: str
    changed_paths: list[str]
    created_at: datetime


class ProvenanceEdgeView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    source_version_id: str
    target_version_id: str
    relation: str
    created_at: datetime


class RerunRelationshipView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    source_stage_run_id: str
    rerun_stage_run_id: str
    source_event_id: str
    created_at: datetime


class ProvenanceGraphView(BaseModel):
    events: list[ReviewEventView] = Field(default_factory=list)
    edges: list[ProvenanceEdgeView] = Field(default_factory=list)
    edits: list[ResearcherEditView] = Field(default_factory=list)
    reruns: list[RerunRelationshipView] = Field(default_factory=list)
