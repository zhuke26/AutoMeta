from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    original_name: str
    mime_type: str
    size_bytes: int
    parse_status: str
    created_at: datetime
