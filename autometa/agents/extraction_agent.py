"""
ExtractionAgent — extracts structured data from uploaded PDFs.

Four-step pipeline:
  Step 1. Parse PDFs using Docling              (pdf_parser.parse_pdfs)
  Step 2. Chunk text + BM25 semantic filtering   (chunker.chunk_document + build_context)
  Step 3. LLM extraction with configured model  (batch_function_call_llm with model override)
     3a. Study characteristics (one row per paper)
     3b. Study results (multiple rows per paper)
  Step 4. Assemble output tables                 (deterministic aggregation)
"""

import json
import logging
from pathlib import Path
from typing import Generator, List

from autometa.agents.base_agent import BaseAgent
from autometa.config import AgentStage, get_settings
from autometa.extraction import validate_source_reference
from autometa.prompts.extraction import (
    RESULT_TARGET_PLANNING,
    RESULT_TARGET_PLANNING_TOOL,
    STUDY_CHARACTERISTICS_EXTRACTION,
    STUDY_RESULTS_EXTRACTION,
)
from autometa.schemas.extraction_models import (
    CharacteristicsRow,
    ExtractionFieldDefinition,
    ExtractionOutput,
    ExtractionSummary,
    FieldExtraction,
    ParsedPDF,
    ResultsRow,
    TextChunk,
)
from autometa.schemas.models import PICODefinition
from autometa.tools.chunker import (
    build_context_chunks,
    chunk_document,
    format_chunks_with_citations,
)
from autometa.tools.llm import batch_function_call_llm
from autometa.tools.pdf_parser import (
    get_last_ocr_fallback_files,
    parse_pdf,
    parse_pdfs,
    reset_last_ocr_fallback_files,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schema builders
# ---------------------------------------------------------------------------

def _build_characteristics_tool(field_names: List[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "submit_characteristics",
            "description": (
                f"Submit extracted study characteristics. "
                f"Return exactly {len(field_names)} field extractions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "extractions": {
                        "type": "array",
                        "description": f"Exactly {len(field_names)} field extractions, one per field.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_name": {"type": "string"},
                                "value": {"type": "string", "description": "Extracted value or 'NOT FOUND'"},
                                "citation": {"type": "string", "description": "Verbatim quote from the paper"},
                                "source_id": {"type": "string", "description": "ID of the supplied source block containing the citation"},
                                "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                            },
                            "required": ["field_name", "value", "confidence"],
                        },
                        "minItems": len(field_names),
                        "maxItems": len(field_names),
                    }
                },
                "required": ["extractions"],
            },
        },
    }


def _build_results_tool(field_names: List[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "submit_results",
            "description": (
                "Submit extracted study results. "
                "One or more rows per paper (one per outcome/subgroup/timepoint)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "description": "One row per distinct outcome/subgroup/timepoint.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "outcome_label": {
                                    "type": "string",
                                    "description": "Descriptive label, e.g. 'Primary: BMI at 6 months'",
                                },
                                "extractions": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "field_name": {"type": "string"},
                                            "value": {"type": "string"},
                                            "citation": {"type": "string"},
                                            "source_id": {"type": "string", "description": "ID of the supplied source block containing the citation"},
                                            "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                                        },
                                        "required": ["field_name", "value", "confidence"],
                                    },
                                },
                            },
                            "required": ["outcome_label", "extractions"],
                        },
                        "minItems": 1,
                    }
                },
                "required": ["rows"],
            },
        },
    }


# ---------------------------------------------------------------------------
# Helper: format field definitions for the prompt
# ---------------------------------------------------------------------------

RESULT_RETRIEVAL_TERMS = (
    "results outcome outcomes primary secondary endpoint endpoints baseline follow-up follow up "
    "timepoint week weeks month months arm group intervention control placebo usual care "
    "mean sd standard deviation n sample odds ratio risk ratio relative risk confidence interval "
    "95% ci p-value effect estimate table"
)


def _format_fields_text(fields: List[ExtractionFieldDefinition]) -> str:
    lines = []
    for i, f in enumerate(fields, start=1):
        if f.description:
            lines.append(f"{i}. {f.name} — {f.description}")
        else:
            lines.append(f"{i}. {f.name}")
    return "\n".join(lines)


def _parse_model_chain(model_config: str) -> List[str]:
    """
    Parse model chain from a config string.
    Supports a comma-separated fallback list, e.g.:
      "primary-model,fallback-model"
    """
    if not model_config:
        return []
    models = [part.strip() for part in model_config.split(",")]
    models = [model for model in models if model]
    return models


# ---------------------------------------------------------------------------
# ExtractionAgent
# ---------------------------------------------------------------------------

class ExtractionAgent(BaseAgent):
    """
    Extracts structured study data from uploaded PDFs using Docling + BM25 + LLM.

    Usage::

        agent = ExtractionAgent()
        result = agent.run(
            file_paths=["paper1.pdf", "paper2.pdf"],
            pico=PICODefinition(P="...", I="...", C="...", O="..."),
            char_fields=[ExtractionFieldDefinition(name="Author"), ...],
            result_fields=[ExtractionFieldDefinition(name="Effect Size"), ...],
        )
    """

    def __init__(self):
        super().__init__("ExtractionAgent")
        configured_model = get_settings().model_for(AgentStage.EXTRACTION)
        self._model_chain = _parse_model_chain(configured_model) or [configured_model]
        self._model = self._model_chain[0]
        logger.info(
            "[ExtractionAgent] Extraction model chain: %s",
            " -> ".join(self._model_chain),
        )

    def _batch_function_call_with_fallback(
        self,
        prompt_template: str,
        batch_inputs: list,
        tool: dict,
        max_concurrency: int,
        phase: str,
    ) -> List[dict]:
        """
        Call batch function-calling with model fallback.
        Tries models in self._model_chain order until one succeeds.
        """
        last_exc = None
        total = len(self._model_chain)

        for i, model_name in enumerate(self._model_chain, start=1):
            try:
                logger.info(
                    "[ExtractionAgent] %s using model: %s (%d/%d)",
                    phase, model_name, i, total,
                )
                outputs = batch_function_call_llm(
                    prompt_template,
                    batch_inputs,
                    tool=tool,
                    max_concurrency=max_concurrency,
                    model=model_name,
                )
                self._model = model_name
                logger.info(
                    "[ExtractionAgent] %s succeeded with model: %s",
                    phase, model_name,
                )
                return outputs
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "[ExtractionAgent] %s failed with model %s (%d/%d): %s",
                    phase, model_name, i, total, exc,
                )

        if last_exc:
            raise last_exc
        return []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        file_paths: List[str],
        pico: PICODefinition,
        char_fields: List[ExtractionFieldDefinition],
        result_fields: List[ExtractionFieldDefinition],
        file_ids: List[str] | None = None,
        top_k: int = 15,
        max_concurrency: int = 10,
    ) -> ExtractionOutput:
        self.reset()

        if not file_paths:
            return ExtractionOutput()

        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}

        # Step 1: Parse PDFs
        parsed_docs = self._run_step(
            "parse_pdfs", self._parse_pdfs, file_paths, file_ids,
        )

        # Step 2: Chunk + semantic filtering
        char_contexts, result_contexts, char_sources, result_sources = self._run_step(
            "chunk_and_retrieve",
            self._chunk_and_retrieve,
            parsed_docs, char_fields, result_fields, top_k, pico.O,
        )

        # Step 3a: Extract characteristics
        characteristics = []
        if char_fields:
            characteristics = self._run_step(
                "extract_characteristics",
                self._extract_characteristics,
                parsed_docs, char_contexts, char_sources, pico_dict, char_fields, max_concurrency,
            )

        # Step 3b: Extract results
        results = []
        if result_fields:
            planned_targets = self._run_step(
                "plan_result_targets",
                self._plan_result_targets,
                parsed_docs, result_contexts, pico_dict, result_fields, max_concurrency,
            )
            results = self._run_step(
                "extract_results",
                self._extract_results,
                parsed_docs, result_contexts, result_sources, pico_dict, result_fields, max_concurrency, planned_targets,
            )

        output = ExtractionOutput(characteristics=characteristics, results=results)

        logger.info(
            "[ExtractionAgent] Done: %d papers → %d char rows, %d result rows (%.1fs)",
            len(file_paths), len(characteristics), len(results), self.state.elapsed,
        )
        return output

    # ------------------------------------------------------------------
    # Step 1: PDF Parsing
    # ------------------------------------------------------------------

    def _parse_pdfs(
        self,
        file_paths: List[str],
        file_ids: List[str] | None = None,
    ) -> List[ParsedPDF]:
        docs = parse_pdfs(file_paths, file_ids=file_ids)
        logger.info(
            "[ExtractionAgent] Parsed %d/%d PDFs successfully",
            sum(1 for d in docs if d.markdown_text), len(file_paths),
        )
        return docs

    # ------------------------------------------------------------------
    # Step 2: Chunk + BM25 Retrieve
    # ------------------------------------------------------------------

    def _chunk_and_retrieve(
        self,
        docs: List[ParsedPDF],
        char_fields: List[ExtractionFieldDefinition],
        result_fields: List[ExtractionFieldDefinition],
        top_k: int,
        pico_outcome: str = "",
    ) -> tuple[List[str], List[str], List[List[TextChunk]], List[List[TextChunk]]]:
        """
        For each document, chunk body text and retrieve relevant context.

        Returns:
            (char_contexts, result_contexts) — each is a list of formatted
            chunks_text strings, one per document.
        """
        char_field_tuples = [(f.name, f.description) for f in char_fields]
        result_field_tuples = [(f.name, f.description) for f in result_fields]

        char_contexts = []
        result_contexts = []
        char_sources: List[List[TextChunk]] = []
        result_sources: List[List[TextChunk]] = []

        for doc in docs:
            if not doc.markdown_text:
                char_contexts.append("(PDF parsing failed — no content available)")
                result_contexts.append("(PDF parsing failed — no content available)")
                char_sources.append([])
                result_sources.append([])
                continue

            body_chunks, table_chunks = chunk_document(doc)

            # Characteristics context
            if char_field_tuples:
                char_chunks = build_context_chunks(
                    body_chunks, table_chunks, char_field_tuples, top_k=top_k,
                )
                char_contexts.append(format_chunks_with_citations(char_chunks))
                char_sources.append(char_chunks)
            else:
                char_contexts.append("")
                char_sources.append([])

            # Results context: include PICO outcome and common statistical terms
            # so retrieval is not driven only by user field labels such as "OR".
            if result_field_tuples:
                result_queries = list(result_field_tuples)
                result_queries.append(("Review outcome", pico_outcome))
                result_queries.append(("PICO outcome", pico_outcome))
                result_queries.append(("Results vocabulary", RESULT_RETRIEVAL_TERMS))
                result_chunks = build_context_chunks(
                    body_chunks, table_chunks, result_queries, top_k=top_k,
                )
                result_contexts.append(format_chunks_with_citations(result_chunks))
                result_sources.append(result_chunks)
            else:
                result_contexts.append("")
                result_sources.append([])

        logger.info(
            "[ExtractionAgent] Chunked %d documents, contexts ready", len(docs),
        )
        return char_contexts, result_contexts, char_sources, result_sources

    # ------------------------------------------------------------------
    # Step 3a: Extract Characteristics
    # ------------------------------------------------------------------

    def _extract_characteristics(
        self,
        docs: List[ParsedPDF],
        char_contexts: List[str],
        char_sources: List[List[TextChunk]],
        pico_dict: dict,
        char_fields: List[ExtractionFieldDefinition],
        max_concurrency: int,
    ) -> List[CharacteristicsRow]:
        field_names = [f.name for f in char_fields]
        fields_text = _format_fields_text(char_fields)
        tool = _build_characteristics_tool(field_names)

        batch_inputs = []
        valid_indices = []
        for i, doc in enumerate(docs):
            if not doc.markdown_text:
                continue
            batch_inputs.append({
                **pico_dict,
                "fields_text": fields_text,
                "chunks_text": char_contexts[i],
            })
            valid_indices.append(i)

        if not batch_inputs:
            return [CharacteristicsRow(filename=d.filename) for d in docs]

        raw_results = self._batch_function_call_with_fallback(
            prompt_template=STUDY_CHARACTERISTICS_EXTRACTION,
            batch_inputs=batch_inputs,
            tool=tool,
            max_concurrency=max_concurrency,
            phase="extract_characteristics",
        )

        # Map results back to all documents
        result_map = {}
        for idx, raw in zip(valid_indices, raw_results):
            result_map[idx] = raw

        rows = []
        for i, doc in enumerate(docs):
            raw = result_map.get(i, {})
            extractions = self._parse_characteristics(raw, field_names, char_sources[i])
            rows.append(CharacteristicsRow(filename=doc.filename, extractions=extractions))

        return rows

    def _parse_characteristics(
        self,
        raw: dict,
        field_names: List[str],
        chunks: List[TextChunk] | None = None,
    ) -> List[FieldExtraction]:
        raw_extractions = raw.get("extractions", [])

        # Build lookup by field_name
        lookup = {}
        for ext in raw_extractions:
            if isinstance(ext, dict):
                name = ext.get("field_name", "")
                lookup[name] = ext

        result = []
        for fn in field_names:
            ext = lookup.get(fn, {})
            value = ext.get("value", "NOT FOUND")
            citation = ext.get("citation", "")
            result.append(FieldExtraction(
                field_name=fn,
                value=value,
                citation=citation,
                confidence=ext.get("confidence", "LOW") if value != "NOT FOUND" else "LOW",
                source_id=ext.get("source_id") or None,
                source=validate_source_reference(
                    citation if value != "NOT FOUND" else "",
                    ext.get("source_id"),
                    chunks or [],
                ),
            ))
        return result

    # ------------------------------------------------------------------
    # Step 3b-1: Plan result targets
    # ------------------------------------------------------------------

    def _plan_result_targets(
        self,
        docs: List[ParsedPDF],
        result_contexts: List[str],
        pico_dict: dict,
        result_fields: List[ExtractionFieldDefinition],
        max_concurrency: int,
    ) -> List[List[dict]]:
        fields_text = _format_fields_text(result_fields)
        batch_inputs = []
        valid_indices = []
        for i, doc in enumerate(docs):
            if not doc.markdown_text:
                continue
            batch_inputs.append({
                **pico_dict,
                "fields_text": fields_text,
                "chunks_text": result_contexts[i],
            })
            valid_indices.append(i)

        planned: List[List[dict]] = [[] for _ in docs]
        if not batch_inputs:
            return planned

        raw_results = self._batch_function_call_with_fallback(
            prompt_template=RESULT_TARGET_PLANNING,
            batch_inputs=batch_inputs,
            tool=RESULT_TARGET_PLANNING_TOOL,
            max_concurrency=max_concurrency,
            phase="plan_result_targets",
        )

        for idx, raw in zip(valid_indices, raw_results):
            targets = raw.get("targets", []) if isinstance(raw, dict) else []
            if not isinstance(targets, list):
                targets = []
            planned[idx] = [target for target in targets if isinstance(target, dict)]

        logger.info(
            "[ExtractionAgent] Planned %d result target row(s) across %d documents",
            sum(len(targets) for targets in planned), len(docs),
        )
        return planned


    # ------------------------------------------------------------------
    # Step 3b: Extract Results
    # ------------------------------------------------------------------

    def _extract_results(
        self,
        docs: List[ParsedPDF],
        result_contexts: List[str],
        result_sources: List[List[TextChunk]],
        pico_dict: dict,
        result_fields: List[ExtractionFieldDefinition],
        max_concurrency: int,
        planned_targets: List[List[dict]] | None = None,
    ) -> List[ResultsRow]:
        field_names = [f.name for f in result_fields]
        fields_text = _format_fields_text(result_fields)
        tool = _build_results_tool(field_names)

        batch_inputs = []
        valid_indices = []
        for i, doc in enumerate(docs):
            if not doc.markdown_text:
                continue
            batch_inputs.append({
                **pico_dict,
                "fields_text": fields_text,
                "chunks_text": result_contexts[i],
                "planned_targets_json": json.dumps(
                    (planned_targets or [[] for _ in docs])[i],
                    ensure_ascii=False,
                    indent=2,
                ),
            })
            valid_indices.append(i)

        if not batch_inputs:
            return []

        raw_results = self._batch_function_call_with_fallback(
            prompt_template=STUDY_RESULTS_EXTRACTION,
            batch_inputs=batch_inputs,
            tool=tool,
            max_concurrency=max_concurrency,
            phase="extract_results",
        )

        all_rows = []
        for idx, raw in zip(valid_indices, raw_results):
            doc = docs[idx]
            rows = self._parse_results(
                raw,
                doc.filename,
                field_names,
                result_sources[idx],
            )
            all_rows.extend(rows)

        return all_rows

    def _parse_results(
        self,
        raw: dict,
        filename: str,
        field_names: List[str],
        chunks: List[TextChunk] | None = None,
    ) -> List[ResultsRow]:
        raw_rows = raw.get("rows", [])
        if not raw_rows:
            return []

        result_rows = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            outcome_label = raw_row.get("outcome_label", "")
            raw_extractions = raw_row.get("extractions", [])

            # Build lookup
            lookup = {}
            for ext in raw_extractions:
                if isinstance(ext, dict):
                    name = ext.get("field_name", "")
                    lookup[name] = ext

            extractions = []
            for fn in field_names:
                ext = lookup.get(fn, {})
                value = ext.get("value", "NOT FOUND")
                citation = ext.get("citation", "")
                extractions.append(FieldExtraction(
                    field_name=fn,
                    value=value,
                    citation=citation,
                    confidence=ext.get("confidence", "LOW") if value != "NOT FOUND" else "LOW",
                    source_id=ext.get("source_id") or None,
                    source=validate_source_reference(
                        citation if value != "NOT FOUND" else "",
                        ext.get("source_id"),
                        chunks or [],
                    ),
                ))

            result_rows.append(ResultsRow(
                filename=filename,
                outcome_label=outcome_label,
                extractions=extractions,
            ))

        return result_rows

    # ------------------------------------------------------------------
    # Streaming entry point (yields SSE-friendly dicts)
    # ------------------------------------------------------------------

    def run_stream(
        self,
        file_paths: List[str],
        pico: PICODefinition,
        char_fields: List[ExtractionFieldDefinition],
        result_fields: List[ExtractionFieldDefinition],
        top_k: int = 15,
        max_concurrency: int = 10,
    ) -> Generator[dict, None, None]:
        """
        Generator that yields progress events for SSE streaming.

        Event types:
          {"type": "parsing_start",      "data": {"filename": str, "index": i, "total": N}}
          {"type": "parsing",            "data": {"filename": str, "status": "ok"/"failed"}}
          {"type": "parsing_done",       "data": {"total": N, "parsed": M}}
          {"type": "ocr_fallback",       "data": {"message": str, "files": [str, ...], "count": N}}
          {"type": "chunking_done",      "data": {"total_documents": N}}
          {"type": "extraction_start",   "data": {"kind": "characteristics"/"results"}}
          {"type": "paper_extracted",    "data": {"filename": str, "characteristics": {...}, "results": [...]}}
          {"type": "summary",            "data": ExtractionSummary}
          {"type": "done",               "data": ExtractionOutput}
          {"type": "error",              "data": str}
        """
        self.reset()

        if not file_paths:
            yield {"type": "done", "data": ExtractionOutput().model_dump()}
            return

        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}

        # Step 1: Parse PDFs — yield per-file progress as each document finishes.
        parsed_docs = []
        reset_last_ocr_fallback_files()
        for index, file_path in enumerate(file_paths, start=1):
            filename = Path(file_path).name
            yield {
                "type": "parsing_start",
                "data": {"filename": filename, "index": index, "total": len(file_paths)},
            }
            try:
                doc = parse_pdf(file_path)
                logger.info(
                    "[ExtractionAgent] Parsed %s: %d chars, %d tables, %d pages",
                    filename,
                    len(doc.markdown_text),
                    len(doc.tables),
                    doc.num_pages,
                )
                parsed_docs.append(doc)
                yield {
                    "type": "parsing",
                    "data": {
                        "filename": filename,
                        "status": "ok" if doc.markdown_text else "failed",
                        "index": index,
                        "total": len(file_paths),
                        "pages": doc.num_pages,
                    },
                }
            except Exception as exc:
                logger.exception("run_stream: parse_pdf failed for %s", filename)
                parsed_docs.append(ParsedPDF(filename=filename, markdown_text="", tables=[], num_pages=0))
                yield {
                    "type": "parsing",
                    "data": {
                        "filename": filename,
                        "status": "failed",
                        "index": index,
                        "total": len(file_paths),
                        "error": str(exc),
                    },
                }

        parsed_count = sum(1 for d in parsed_docs if d.markdown_text)
        yield {"type": "parsing_done", "data": {"total": len(file_paths), "parsed": parsed_count}}

        fallback_files = get_last_ocr_fallback_files()
        if fallback_files:
            logger.warning(
                "[ExtractionAgent] OCR fallback used for %d file(s): %s",
                len(fallback_files),
                ", ".join(fallback_files),
            )
            yield {
                "type": "ocr_fallback",
                "data": {
                    "message": "OCR fallback used",
                    "files": fallback_files,
                    "count": len(fallback_files),
                },
            }

        # Step 2: Chunk + retrieve
        try:
            char_contexts, result_contexts, char_sources, result_sources = self._chunk_and_retrieve(
                parsed_docs, char_fields, result_fields, top_k, pico.O,
            )
            yield {"type": "chunking_done", "data": {"total_documents": len(parsed_docs)}}
        except Exception as exc:
            logger.exception("run_stream: chunking failed")
            yield {"type": "error", "data": str(exc)}
            return

        # Step 3a: Extract characteristics
        characteristics = []
        if char_fields:
            try:
                yield {"type": "extraction_start", "data": {"kind": "characteristics"}}
                characteristics = self._extract_characteristics(
                    parsed_docs, char_contexts, char_sources, pico_dict, char_fields, max_concurrency,
                )
            except Exception as exc:
                logger.exception("run_stream: characteristics extraction failed")
                yield {"type": "error", "data": str(exc)}
                return

        # Step 3b: Plan and extract results
        results = []
        if result_fields:
            try:
                yield {"type": "result_targets_start", "data": {"kind": "results"}}
                planned_targets = self._plan_result_targets(
                    parsed_docs, result_contexts, pico_dict, result_fields, max_concurrency,
                )
                yield {
                    "type": "result_targets_done",
                    "data": {
                        "total_targets": sum(len(targets) for targets in planned_targets),
                        "per_file": [
                            {"filename": doc.filename, "targets": len(targets)}
                            for doc, targets in zip(parsed_docs, planned_targets)
                        ],
                    },
                }
                yield {"type": "extraction_start", "data": {"kind": "results"}}
                results = self._extract_results(
                    parsed_docs, result_contexts, result_sources, pico_dict, result_fields, max_concurrency, planned_targets,
                )
            except Exception as exc:
                logger.exception("run_stream: results extraction failed")
                yield {"type": "error", "data": str(exc)}
                return

        # Yield per-paper combined results
        char_map = {row.filename: row for row in characteristics}
        results_map: dict = {}
        for row in results:
            results_map.setdefault(row.filename, []).append(row)

        for doc in parsed_docs:
            char_row = char_map.get(doc.filename)
            res_rows = results_map.get(doc.filename, [])
            yield {
                "type": "paper_extracted",
                "data": {
                    "filename": doc.filename,
                    "characteristics": char_row.model_dump() if char_row else None,
                    "results": [r.model_dump() for r in res_rows],
                },
            }

        # Summary
        summary = ExtractionSummary(
            total_papers=len(file_paths),
            papers_parsed=sum(1 for d in parsed_docs if d.markdown_text),
            papers_extracted=len(characteristics),
            total_characteristics_fields=len(char_fields),
            total_results_fields=len(result_fields),
        )
        yield {"type": "summary", "data": summary.model_dump()}

        output = ExtractionOutput(characteristics=characteristics, results=results)
        yield {"type": "done", "data": output.model_dump()}
