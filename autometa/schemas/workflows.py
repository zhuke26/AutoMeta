from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ProtocolWorkflowRequest(BaseModel):
    research_question: str = Field(min_length=10, max_length=4000)


class SearchQueryWorkflowRequest(BaseModel):
    strategy_mode: Literal["field_tagged_balanced"] = "field_tagged_balanced"


class SearchRunWorkflowRequest(BaseModel):
    retmax: int = Field(default=1000, ge=1, le=100000)
    fetch_all: bool = False
    min_year: int | None = Field(default=None, ge=1900, le=2100)
    max_year: int | None = Field(default=None, ge=1900, le=2100)

    @model_validator(mode="after")
    def validate_years(self):
        if self.min_year and self.max_year and self.min_year > self.max_year:
            raise ValueError("Start year must be earlier than or equal to end year")
        return self
