from __future__ import annotations

from autometa.schemas.extraction_models import ParsedPDF, SourceLocator, TextChunk


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
    source: str = "body",
    *,
    source_id: str = "source",
    locator: SourceLocator | None = None,
) -> list[TextChunk]:
    if not text or not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_str = text[start:end]
        if end < len(text):
            boundary_start = int(chunk_size * 0.8)
            boundary = chunk_str[boundary_start:]
            import re

            match = re.search(r"[.!?]\s", boundary)
            if match:
                end = start + boundary_start + match.end()
                chunk_str = text[start:end]
        stripped = chunk_str.strip()
        if stripped:
            chunk_id = f"{source_id}:{len(chunks)}"
            chunk_locator = (
                locator.model_copy(
                    update={
                        "source_id": chunk_id,
                        "text_start": start,
                        "text_end": end,
                    }
                )
                if locator
                else None
            )
            chunks.append(
                TextChunk(
                    text=stripped,
                    source=source,
                    start_char=start,
                    end_char=end,
                    source_id=chunk_id,
                    locator=chunk_locator,
                )
            )
        next_start = end - overlap
        start = end if next_start <= start else next_start
    return chunks


def chunk_document(
    document: ParsedPDF | str,
    tables: list[str] | None = None,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> tuple[list[TextChunk], list[TextChunk]]:
    if isinstance(document, ParsedPDF):
        body_chunks: list[TextChunk] = []
        table_chunks: list[TextChunk] = []
        elements = document.elements
        if not elements and document.markdown_text:
            return chunk_document(
                document.markdown_text, document.tables, chunk_size, overlap
            )
        for element in elements:
            if element.locator.element_type == "table":
                table_chunks.append(
                    TextChunk(
                        text=element.text,
                        source="table",
                        start_char=0,
                        end_char=len(element.text),
                        source_id=element.source_id,
                        locator=element.locator,
                    )
                )
            else:
                body_chunks.extend(
                    chunk_text(
                        element.text,
                        chunk_size,
                        overlap,
                        source="body",
                        source_id=element.source_id,
                        locator=element.locator,
                    )
                )
        return body_chunks, table_chunks
    body_chunks = chunk_text(document, chunk_size, overlap, source="body")
    table_chunks = [
        TextChunk(
            text=value.strip(),
            source="table",
            start_char=0,
            end_char=len(value.strip()),
            source_id=f"table-{index}",
        )
        for index, value in enumerate(tables or [])
        if value.strip()
    ]
    return body_chunks, table_chunks


def retrieve_relevant_chunks(
    body_chunks: list[TextChunk],
    query: str,
    top_k: int = 15,
) -> list[TextChunk]:
    from rank_bm25 import BM25Okapi

    if not body_chunks:
        return []
    corpus = [chunk.text.lower().split() for chunk in body_chunks]
    scores = BM25Okapi(corpus).get_scores(query.lower().split())
    indices = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)[
        :top_k
    ]
    return [body_chunks[index] for index in indices]


def build_context_chunks(
    body_chunks: list[TextChunk],
    table_chunks: list[TextChunk],
    field_names_and_descs: list[tuple[str, str]],
    top_k: int = 15,
) -> list[TextChunk]:
    query = " ".join(
        part
        for name, description in field_names_and_descs
        for part in (name, description)
        if part
    )
    selected = retrieve_relevant_chunks(body_chunks, query, top_k=top_k)
    seen: set[str] = set()
    merged = []
    for chunk in selected + table_chunks:
        if chunk.text not in seen:
            seen.add(chunk.text)
            merged.append(chunk)
    return merged


def format_chunks_with_citations(chunks: list[TextChunk]) -> str:
    if not chunks:
        return "(No relevant content found)"
    return "\n\n".join(
        f'<source id="{chunk.source_id}"><content>{chunk.text}</content></source>'
        for chunk in chunks
    )
