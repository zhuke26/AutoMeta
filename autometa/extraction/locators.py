from __future__ import annotations

import re

from autometa.schemas.extraction_models import SourceLocator, TextChunk


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _quotation_only(citation: str) -> SourceLocator:
    return SourceLocator(quotation=citation)


def validate_source_reference(
    citation: str,
    source_id: str | None,
    chunks: list[TextChunk],
) -> SourceLocator | None:
    quotation = citation.strip()
    if not quotation or quotation.casefold() == "not found":
        return None
    normalized_quote = _normalized(quotation)
    if source_id:
        chunk = next((item for item in chunks if item.source_id == source_id), None)
        if (
            chunk is not None
            and chunk.locator is not None
            and normalized_quote in _normalized(chunk.text)
        ):
            return chunk.locator.model_copy(update={
                "source_id": source_id,
                "quotation": quotation,
            })
        return _quotation_only(quotation)
    matches = [
        chunk
        for chunk in chunks
        if chunk.locator is not None and normalized_quote in _normalized(chunk.text)
    ]
    if len(matches) == 1:
        return matches[0].locator.model_copy(update={
            "source_id": matches[0].source_id or None,
            "quotation": quotation,
        })
    return _quotation_only(quotation)
