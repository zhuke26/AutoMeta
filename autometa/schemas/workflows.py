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


class ScreeningPaperInput(BaseModel):
    pmid: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=2000)
    abstract: str = ""
    authors: str | None = None
    year: str | None = None
    journal: str | None = None
    publication_type: str | None = None


class ScreeningRecordsImportRequest(BaseModel):
    papers: list[ScreeningPaperInput] = Field(min_length=1)
    source_format: Literal["json", "csv", "pubmed"]


class ScreeningRunWorkflowRequest(BaseModel):
    study_design_filter: Literal["rct_only", "obs_only", "both"] = "both"
    max_concurrency: int = Field(default=50, ge=1, le=200)
