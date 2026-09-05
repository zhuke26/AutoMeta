from typing import List, Literal

from pydantic import BaseModel, Field, model_validator


class ExtractionFieldDefinition(BaseModel):
    name: str = Field(description="Field name, e.g. 'Sample Size' or 'Effect Size'")
    description: str = Field(
        default="",
        description="Optional description guiding the LLM on what to extract",
    )


class ParsedPDF(BaseModel):
    filename: str
    markdown_text: str = Field(
        default="", description="Full text converted to Markdown"
    )
    tables: List[str] = Field(
        default_factory=list,
        description="Tables extracted as Markdown-formatted strings",
    )
    num_pages: int = 0
    file_id: str | None = None
    parser_name: str = "unknown"
    parser_version: str = ""
    elements: List["DocumentElement"] = Field(default_factory=list)


class BoundingBox(BaseModel):
    left: float
    bottom: float
    right: float
    top: float
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self):
        if not (
            0 <= self.left < self.right <= self.page_width
            and 0 <= self.bottom < self.top <= self.page_height
        ):
            raise ValueError("Bounding box must lie within the PDF page")
        return self


class SourceLocator(BaseModel):
    file_id: str | None = None
    source_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    element_type: Literal["body", "table", "unknown"] = "unknown"
    table_index: int | None = Field(default=None, ge=0)
    row_index: int | None = Field(default=None, ge=0)
    column_index: int | None = Field(default=None, ge=0)
    bbox: BoundingBox | None = None
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, ge=0)
    parser_name: str = "unknown"
    parser_version: str = ""
    extraction_type: Literal["direct", "derived"] = "direct"
    derivation: str = ""
    quotation: str = ""

    @model_validator(mode="after")
    def validate_table_metadata(self):
        if self.element_type != "table" and any(
            value is not None
            for value in (self.table_index, self.row_index, self.column_index)
        ):
            raise ValueError("Table indices require a table element")
        if self.text_start is not None and self.text_end is not None:
            if self.text_end < self.text_start:
                raise ValueError("Text span end must not precede its start")
        return self


class DocumentElement(BaseModel):
    source_id: str
    text: str
    locator: SourceLocator


class TextChunk(BaseModel):
    text: str
    source: str = Field(description="'body' or 'table'")
    start_char: int = 0
    end_char: int = 0
    source_id: str = ""
    locator: SourceLocator | None = None


class FieldExtraction(BaseModel):
    field_name: str
    value: str = Field(default="NOT FOUND", description="Extracted raw value")
    citation: str = Field(
        default="",
        description="Verbatim text from the paper supporting this extraction",
    )
    confidence: str = Field(
        default="LOW",
        description="HIGH | MEDIUM | LOW",
    )
    source_id: str | None = None
    source: SourceLocator | None = None


class CharacteristicsRow(BaseModel):
    filename: str
    extractions: List[FieldExtraction] = Field(default_factory=list)


class ResultsRow(BaseModel):
    filename: str
    outcome_label: str = Field(
        default="",
        description="Label for this outcome group, e.g. 'Primary: BMI at 6 months'",
    )
    extractions: List[FieldExtraction] = Field(default_factory=list)


class ExtractionOutput(BaseModel):
    characteristics: List[CharacteristicsRow] = Field(default_factory=list)
    results: List[ResultsRow] = Field(default_factory=list)


class ExtractionSummary(BaseModel):
    total_papers: int = 0
    papers_parsed: int = 0
    papers_extracted: int = 0
    total_characteristics_fields: int = 0
    total_results_fields: int = 0
