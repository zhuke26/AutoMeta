from autometa.agents.extraction_agent import ExtractionAgent
from autometa.schemas.extraction_models import SourceLocator, TextChunk


def chunks():
    return [TextChunk(
        source_id="body-1:0",
        text="We randomized 120 participants.",
        source="body",
        locator=SourceLocator(
            file_id="file-1",
            source_id="body-1:0",
            page_number=3,
            element_type="body",
            parser_name="docling",
            parser_version="2.0",
        ),
    )]


def test_characteristic_source_id_is_validated_against_supplied_chunk() -> None:
    agent = object.__new__(ExtractionAgent)
    result = agent._parse_characteristics(
        {"extractions": [{
            "field_name": "Sample size",
            "value": "120",
            "citation": "We randomized 120 participants.",
            "source_id": "body-1:0",
            "confidence": "HIGH",
        }]},
        ["Sample size"],
        chunks(),
    )
    assert result[0].source is not None
    assert result[0].source.file_id == "file-1"
    assert result[0].source.page_number == 3


def test_mismatched_source_id_and_not_found_do_not_gain_location() -> None:
    agent = object.__new__(ExtractionAgent)
    mismatched = agent._parse_characteristics(
        {"extractions": [{
            "field_name": "Sample size",
            "value": "120",
            "citation": "Text not in source.",
            "source_id": "body-1:0",
            "confidence": "HIGH",
        }]},
        ["Sample size"],
        chunks(),
    )[0]
    missing = agent._parse_characteristics(
        {"extractions": [{
            "field_name": "Sample size",
            "value": "NOT FOUND",
            "citation": "",
            "source_id": "body-1:0",
            "confidence": "HIGH",
        }]},
        ["Sample size"],
        chunks(),
    )[0]
    assert mismatched.source is not None
    assert mismatched.source.page_number is None
    assert missing.source is None
