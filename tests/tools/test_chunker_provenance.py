from autometa.schemas.extraction_models import (
    BoundingBox,
    DocumentElement,
    ParsedPDF,
    SourceLocator,
)
from autometa.tools.chunker import chunk_document, format_chunks_with_citations


def test_chunking_preserves_element_locator_and_source_id() -> None:
    locator = SourceLocator(
        file_id="file-1",
        source_id="body-1",
        page_number=2,
        element_type="body",
        bbox=BoundingBox(
            left=10,
            bottom=20,
            right=200,
            top=80,
            page_width=612,
            page_height=792,
        ),
        parser_name="docling",
        parser_version="2.0",
    )
    document = ParsedPDF(
        filename="study.pdf",
        file_id="file-1",
        elements=[DocumentElement(source_id="body-1", text="Outcome improved significantly.", locator=locator)],
    )

    body, tables = chunk_document(document, chunk_size=100, overlap=0)

    assert tables == []
    assert body[0].source_id == "body-1:0"
    assert body[0].locator.page_number == 2
    formatted = format_chunks_with_citations(body)
    assert '<source id="body-1:0">' in formatted
