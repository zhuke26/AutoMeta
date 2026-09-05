from __future__ import annotations

import logging
import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from autometa.schemas.extraction_models import (
    BoundingBox,
    DocumentElement,
    ParsedPDF,
    SourceLocator,
)

logger = logging.getLogger(__name__)
DOCLING_ARTIFACTS_PATH = os.environ.get("DOCLING_ARTIFACTS_PATH")
DOCLING_DISABLE_OCR = os.environ.get("DOCLING_DISABLE_OCR", "").lower() in {
    "1",
    "true",
    "yes",
}
_OCR_FALLBACK_MODE = False
_LAST_OCR_FALLBACK_FILES: list[str] = []


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"


def _page_size(document, page_number: int) -> tuple[float, float] | None:
    pages = getattr(document, "pages", None)
    if not pages:
        return None
    page = pages.get(page_number) if hasattr(pages, "get") else None
    if page is None and isinstance(pages, (list, tuple)) and page_number <= len(pages):
        page = pages[page_number - 1]
    size = getattr(page, "size", None)
    if size is None:
        return None
    return float(size.width), float(size.height)


def _span(provenance, text_length: int) -> tuple[int | None, int | None]:
    charspan = getattr(provenance, "charspan", None)
    if isinstance(charspan, (tuple, list)) and len(charspan) == 2:
        return int(charspan[0]), min(int(charspan[1]), text_length)
    start = getattr(charspan, "start", None)
    end = getattr(charspan, "end", None)
    if start is not None and end is not None:
        return int(start), min(int(end), text_length)
    return None, None


def _locator(
    document,
    provenance,
    *,
    file_id: str | None,
    source_id: str,
    element_type: str,
    table_index: int | None = None,
) -> SourceLocator:
    page_number = int(getattr(provenance, "page_no", 0) or 0) or None
    bbox = None
    page_size = _page_size(document, page_number) if page_number else None
    raw_box = getattr(provenance, "bbox", None)
    if raw_box is not None and page_size is not None:
        width, height = page_size
        try:
            converted = raw_box.to_bottom_left_origin(height)
            bbox = BoundingBox(
                left=float(converted.l),
                bottom=float(converted.b),
                right=float(converted.r),
                top=float(converted.t),
                page_width=width,
                page_height=height,
            )
        except (AttributeError, TypeError, ValueError):
            bbox = None
    start, end = _span(provenance, 10**9)
    return SourceLocator(
        file_id=file_id,
        source_id=source_id,
        page_number=page_number,
        element_type=element_type,
        table_index=table_index,
        bbox=bbox,
        text_start=start,
        text_end=end,
        parser_name="docling",
        parser_version=_package_version("docling"),
    )


def _elements_from_docling(
    document, file_id: str | None = None
) -> tuple[list[DocumentElement], list[str]]:
    elements: list[DocumentElement] = []
    for index, item in enumerate(getattr(document, "texts", []) or []):
        text = str(getattr(item, "text", "") or "").strip()
        if not text:
            continue
        provenance_items = list(getattr(item, "prov", []) or [])
        provenance = provenance_items[0] if provenance_items else None
        source_id = f"body-{index}"
        locator = (
            _locator(
                document,
                provenance,
                file_id=file_id,
                source_id=source_id,
                element_type="body",
            )
            if provenance is not None
            else SourceLocator(
                file_id=file_id,
                source_id=source_id,
                element_type="body",
                parser_name="docling",
                parser_version=_package_version("docling"),
            )
        )
        elements.append(
            DocumentElement(source_id=source_id, text=text, locator=locator)
        )

    tables: list[str] = []
    for index, table in enumerate(getattr(document, "tables", []) or []):
        try:
            text = table.export_to_dataframe(doc=document).to_markdown(index=False)
        except Exception:
            try:
                text = table.export_to_html(doc=document)
            except Exception:
                logger.warning("Failed to export a Docling table")
                continue
        tables.append(text)
        source_id = f"table-{index}"
        provenance_items = list(getattr(table, "prov", []) or [])
        provenance = provenance_items[0] if provenance_items else None
        locator = (
            _locator(
                document,
                provenance,
                file_id=file_id,
                source_id=source_id,
                element_type="table",
                table_index=index,
            )
            if provenance is not None
            else SourceLocator(
                file_id=file_id,
                source_id=source_id,
                element_type="table",
                table_index=index,
                parser_name="docling",
                parser_version=_package_version("docling"),
            )
        )
        elements.append(
            DocumentElement(source_id=source_id, text=text, locator=locator)
        )
    return elements, tables


def _convert_pdf(file_path: str, do_ocr: bool, file_id: str | None = None) -> ParsedPDF:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_table_structure = True
    options.do_ocr = do_ocr
    if DOCLING_ARTIFACTS_PATH:
        options.artifacts_path = DOCLING_ARTIFACTS_PATH
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    document = converter.convert(file_path).document
    elements, tables = _elements_from_docling(document, file_id)
    return ParsedPDF(
        filename=Path(file_path).name,
        file_id=file_id,
        markdown_text=document.export_to_markdown(),
        tables=tables,
        num_pages=len(document.pages) if document.pages else 0,
        parser_name="docling",
        parser_version=_package_version("docling"),
        elements=elements,
    )


def _extract_pdfium_pages(file_path: str) -> list[tuple[str, float, float]]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(file_path)
    pages = []
    try:
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            width, height = page.get_size()
            text = page.get_textpage().get_text_range() or ""
            pages.append((text.strip(), float(width), float(height)))
    finally:
        pdf.close()
    return pages


def _convert_pdf_text_fallback(file_path: str, file_id: str | None = None) -> ParsedPDF:
    pages = _extract_pdfium_pages(file_path)
    elements = []
    markdown_pages = []
    for index, (text, width, height) in enumerate(pages, start=1):
        if not text:
            continue
        source_id = f"page-{index}"
        markdown_pages.append(f"## Page {index}\n\n{text}")
        elements.append(
            DocumentElement(
                source_id=source_id,
                text=text,
                locator=SourceLocator(
                    file_id=file_id,
                    source_id=source_id,
                    page_number=index,
                    element_type="body",
                    parser_name="pypdfium2",
                    parser_version=_package_version("pypdfium2"),
                ),
            )
        )
    return ParsedPDF(
        filename=Path(file_path).name,
        file_id=file_id,
        markdown_text="\n\n".join(markdown_pages),
        num_pages=len(pages),
        parser_name="pypdfium2",
        parser_version=_package_version("pypdfium2"),
        elements=elements,
    )


def parse_pdf(file_path: str, file_id: str | None = None) -> ParsedPDF:
    global _OCR_FALLBACK_MODE
    if DOCLING_DISABLE_OCR or _OCR_FALLBACK_MODE:
        try:
            return _convert_pdf(file_path, do_ocr=False, file_id=file_id)
        except Exception as error:
            logger.warning(
                "Docling parse without OCR failed for %s: %s", file_path, error
            )
            return _convert_pdf_text_fallback(file_path, file_id)
    try:
        return _convert_pdf(file_path, do_ocr=True, file_id=file_id)
    except Exception as first_error:
        logger.warning("OCR-enabled parse failed for %s: %s", file_path, first_error)
        _OCR_FALLBACK_MODE = True
        _LAST_OCR_FALLBACK_FILES.append(Path(file_path).name)
        try:
            return _convert_pdf(file_path, do_ocr=False, file_id=file_id)
        except Exception as error:
            logger.warning("Docling retry failed for %s: %s", file_path, error)
            return _convert_pdf_text_fallback(file_path, file_id)


def parse_pdfs(
    file_paths: list[str], file_ids: list[str] | None = None
) -> list[ParsedPDF]:
    global _LAST_OCR_FALLBACK_FILES
    _LAST_OCR_FALLBACK_FILES = []
    ids = file_ids or [None] * len(file_paths)
    if len(ids) != len(file_paths):
        raise ValueError("file_ids must match file_paths")
    results = []
    for path, file_id in zip(file_paths, ids):
        try:
            results.append(parse_pdf(path, file_id=file_id))
        except Exception as error:
            logger.error("Failed to parse %s: %s", path, error)
            results.append(ParsedPDF(filename=Path(path).name, file_id=file_id))
    return results


def reset_last_ocr_fallback_files() -> None:
    global _LAST_OCR_FALLBACK_FILES
    _LAST_OCR_FALLBACK_FILES = []


def get_last_ocr_fallback_files() -> list[str]:
    return list(_LAST_OCR_FALLBACK_FILES)
