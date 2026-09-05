from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


class SearchExpansionRequest(BaseModel):
    seed_retmax: int = Field(default=20, ge=5, le=50)
    included_pmids: list[str] = Field(default_factory=list, max_length=100)
    min_year: int | None = Field(default=None, ge=1900, le=2100)
    max_year: int | None = Field(default=None, ge=1900, le=2100)

    @field_validator("included_pmids")
    @classmethod
    def normalize_pmids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            pmid = value.strip()
            if not pmid:
                continue
            if not pmid.isdigit():
                raise ValueError("Known-study PMIDs must contain digits only")
            if pmid not in normalized:
                normalized.append(pmid)
        return normalized

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


class ExtractionFieldInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)


class ExtractionWorkflowRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)
    study_characteristics_fields: list[ExtractionFieldInput] = Field(default_factory=list)
    study_results_fields: list[ExtractionFieldInput] = Field(default_factory=list)
    top_k: int = Field(default=15, ge=1, le=30)
    max_concurrency: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def validate_fields(self):
        if not self.study_characteristics_fields and not self.study_results_fields:
            raise ValueError("At least one extraction field must be defined")
        return self


class MetaPlanWorkflowRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1)
    user_hint: str = Field(default="", max_length=4000)
    sample_rows: int = Field(default=5, ge=1, le=20)
    max_concurrency: int = Field(default=1, ge=1, le=5)


class MetaRunWorkflowRequest(BaseModel):
    confirm_strict_execution: Literal[True] = True
