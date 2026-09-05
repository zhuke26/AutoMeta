from types import SimpleNamespace

from autometa.tools import pdf_parser


class FakeBox:
    def __init__(self, left, bottom, right, top):
        self.l = left
        self.b = bottom
        self.r = right
        self.t = top

    def to_bottom_left_origin(self, _page_height):
        return self


def test_docling_elements_preserve_page_bbox_and_tables() -> None:
    page = SimpleNamespace(size=SimpleNamespace(width=612, height=792))
    text = SimpleNamespace(
        text="Participants were randomized.",
        prov=[SimpleNamespace(page_no=1, bbox=FakeBox(10, 20, 200, 50), charspan=(0, 29))],
    )
    table = SimpleNamespace(
        prov=[SimpleNamespace(page_no=1, bbox=FakeBox(30, 100, 500, 300), charspan=(0, 20))],
        export_to_dataframe=lambda doc: SimpleNamespace(to_markdown=lambda index=False: "| A | B |"),
    )
    document = SimpleNamespace(pages={1: page}, texts=[text], tables=[table])

    elements, tables = pdf_parser._elements_from_docling(document, "file-1")

    assert len(elements) == 2
    assert elements[0].locator.page_number == 1
    assert elements[0].locator.bbox.bottom == 20
    assert elements[1].locator.element_type == "table"
    assert elements[1].locator.table_index == 0
    assert tables == ["| A | B |"]


def test_plain_text_fallback_emits_page_only_elements(monkeypatch) -> None:
    monkeypatch.setattr(
        pdf_parser,
        "_extract_pdfium_pages",
        lambda _path: [("First page", 612.0, 792.0), ("Second page", 612.0, 792.0)],
    )

    parsed = pdf_parser._convert_pdf_text_fallback("study.pdf", file_id="file-1")

    assert parsed.num_pages == 2
    assert [element.locator.page_number for element in parsed.elements] == [1, 2]
    assert all(element.locator.bbox is None for element in parsed.elements)
    assert parsed.parser_name == "pypdfium2"
