from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from autometa.persistence.models import ReviewMode, ReviewStatus


class ReviewCreate(BaseModel):
    name: str
    entry_mode: ReviewMode

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not 1 <= len(name) <= 160:
            raise ValueError("Review name must contain between 1 and 160 characters")
        return name


class ReviewUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return ReviewCreate.validate_name(value)


class ReviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    entry_mode: ReviewMode
    status: ReviewStatus
    current_stage: str | None
    created_at: datetime
    updated_at: datetime


class ReviewList(BaseModel):
    items: list[ReviewSummary]
    total: int
