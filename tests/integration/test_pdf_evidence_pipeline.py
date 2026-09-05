from autometa.extraction.locators import validate_source_reference
from autometa.tools.chunker import chunk_document
from autometa.tools.pdf_parser import _convert_pdf_text_fallback


def write_two_page_pdf(path) -> None:
    streams = [
        b"BT /F1 12 Tf 72 720 Td (Page one background text) Tj ET",
        b"BT /F1 12 Tf 72 680 Td (Primary outcome improved by 2.4 points.) Tj ET",
    ]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(streams[0]), streams[0]),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(streams[1]), streams[1]),
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode())
        data.extend(body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(data)


def test_two_page_pdf_keeps_page_locator_through_validation(tmp_path) -> None:
    path = tmp_path / "evidence.pdf"
    write_two_page_pdf(path)

    document = _convert_pdf_text_fallback(str(path), file_id="file-1")
    body, tables = chunk_document(document, chunk_size=200, overlap=0)
    source = validate_source_reference(
        "Primary outcome improved by 2.4 points.",
        "page-2:0",
        body,
    )

    assert tables == []
    assert document.num_pages == 2
    assert source is not None
    assert source.file_id == "file-1"
    assert source.page_number == 2
    assert source.bbox is None
