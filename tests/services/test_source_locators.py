import pytest
from pydantic import ValidationError

from autometa.extraction.locators import validate_source_reference
from autometa.schemas.extraction_models import BoundingBox, SourceLocator, TextChunk


def located_chunk(source_id: str, text: str, page: int) -> TextChunk:
    return TextChunk(
        source_id=source_id,
        text=text,
        source="body",
        locator=SourceLocator(
            file_id="file-1",
            source_id=source_id,
            page_number=page,
            element_type="body",
            bbox=BoundingBox(
                left=10,
                bottom=20,
                right=200,
                top=60,
                page_width=612,
                page_height=792,
            ),
            parser_name="docling",
            parser_version="2.0",
        ),
    )


def test_valid_source_id_and_quote_preserve_exact_locator() -> None:
    locator = validate_source_reference(
        "We randomized 120 participants.",
        "source-1",
        [located_chunk("source-1", "We randomized   120 participants.", 3)],
    )
    assert locator is not None
    assert locator.page_number == 3
    assert locator.bbox is not None
    assert locator.quotation == "We randomized 120 participants."


def test_unique_quote_can_recover_page_but_ambiguous_quote_cannot() -> None:
    unique = validate_source_reference(
        "Primary outcome improved.",
        None,
        [
            located_chunk("source-1", "Background text", 1),
            located_chunk("source-2", "Primary outcome improved.", 2),
        ],
    )
    ambiguous = validate_source_reference(
        "Repeated quotation",
        None,
        [
            located_chunk("source-1", "Repeated quotation", 1),
            located_chunk("source-2", "Repeated quotation", 2),
        ],
    )
    assert unique is not None and unique.page_number == 2
    assert ambiguous is not None
    assert ambiguous.page_number is None
    assert ambiguous.bbox is None


def test_invalid_source_id_fails_closed_to_quotation_only() -> None:
    locator = validate_source_reference(
        "Exact text",
        "missing-source",
        [located_chunk("source-1", "Exact text", 4)],
    )
    assert locator is not None
    assert locator.quotation == "Exact text"
    assert locator.page_number is None
    assert locator.source_id is None


def test_not_found_has_no_source_locator() -> None:
    assert validate_source_reference("", None, []) is None
    assert validate_source_reference("NOT FOUND", None, []) is None


def test_bbox_and_table_metadata_are_strictly_validated() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(
            left=-1,
            bottom=0,
            right=10,
            top=10,
            page_width=100,
            page_height=100,
        )
    with pytest.raises(ValidationError):
        SourceLocator(element_type="body", table_index=1)
    table = SourceLocator(
        page_number=1,
        element_type="table",
        table_index=0,
        row_index=2,
        column_index=1,
        extraction_type="derived",
        derivation="Calculated from reported arm values",
    )
    assert table.row_index == 2
