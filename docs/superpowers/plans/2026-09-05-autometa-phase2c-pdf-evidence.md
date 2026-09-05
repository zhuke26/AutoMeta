# AutoMeta Phase 2C Source-Linked PDF Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach verifiable page/table/region provenance to extracted values and provide a locally bundled PDF reader that navigates and highlights only locations actually returned by the parser.

**Architecture:** Replace the parser's lossy `(markdown, tables, pages)` tuple with structured document elements carrying optional page and normalized bounding boxes. Retrieval chunks preserve those locators; extraction outputs bind citations to source IDs and validate quotations deterministically before storing a `SourceLocator`. A Review-owned PDF content endpoint feeds a locally bundled PDF.js viewer with strict coordinate, page-only, and quotation-only degradation modes.

**Tech Stack:** Docling, pypdfium2 fallback, Pydantic 2, FastAPI streaming/file responses, existing artifact/provenance services, React 18, TypeScript 5, `pdfjs-dist`, Vitest, Testing Library.

## Global Constraints

- Manual Review-owned PDF upload remains the only source; never fetch publisher, DOI, or PMC full text.
- A locator may contain only parser-provided or deterministically validated information.
- Never infer/fabricate page, table, row, column, text span, or coordinates.
- Coordinates use PDF points plus page width/height and bottom-left origin; the frontend converts them for PDF.js display.
- Coordinate available: open page and highlight region. Page only: open page and show quotation beside it. Quotation only: show `Exact page location unavailable`.
- A model-supplied `source_id` is accepted only when it identifies a supplied chunk and its verbatim quotation occurs in that chunk after whitespace normalization.
- Ambiguous quotation matches do not receive a page or box.
- Persist `file_id`, parser name/version, element type, direct/derived type, derivation text, and validated quotation with every locator.
- PDF bytes and extracted page text never enter job events, provenance metadata, logs, or browser storage.
- PDF content endpoints enforce Review ownership and return no filesystem path.
- Bundle PDF.js and its worker locally; no CDN or remote fonts/assets.
- Use TDD, run render/browser checks at supported widths, commit locally, and never push.

---

### Task 1: Define structured document and source-locator contracts

**Files:**
- Modify: `autometa/schemas/extraction_models.py`
- Create: `autometa/extraction/locators.py`
- Create: `autometa/extraction/__init__.py`
- Create: `tests/services/test_source_locators.py`

**Interfaces:**
- Produces `BoundingBox`, `DocumentElement`, `SourceLocator`, and enriched
  `ParsedPDF`, `TextChunk`, and `FieldExtraction.source`.
- Produces `validate_source_reference(citation, source_id, chunks) -> SourceLocator`.

- [x] Write failing tests for coordinate/page/quotation degradation, normalized
  whitespace quotation validation, invalid source IDs, ambiguous matches, table
  metadata, and bbox bounds.
- [x] Run the focused test and verify RED because locator models/functions do not exist.
- [x] Add models with optional fields and validators: `page_number >= 1`, positive
  page dimensions, bbox within page bounds, and table row/column allowed only for
  `element_type="table"`.
- [x] Implement exact source validation. A valid source ID plus verbatim quote may
  inherit its chunk locator; a unique verbatim quote may inherit a locator without
  source ID; ambiguous/missing quotes retain quotation and parser metadata only.
- [x] Run focused tests/Ruff and commit as `feat: define PDF source locators`.

### Task 2: Preserve Docling and fallback page provenance through chunking

**Files:**
- Modify: `autometa/tools/pdf_parser.py`
- Modify: `autometa/tools/chunker.py`
- Create: `tests/tools/test_pdf_parser_provenance.py`
- Create: `tests/tools/test_chunker_provenance.py`

**Interfaces:**
- Replaces `parse_pdf(path) -> tuple` with `parse_pdf(path) -> ParsedPDF` and
  `parse_pdfs(paths) -> list[ParsedPDF]`.
- `chunk_document(document)` returns `TextChunk` objects with stable source IDs
  and inherited locators.

- [x] Write failing adapter tests using minimal fake Docling documents and a
  generated two-page PDF fallback fixture.
- [x] Verify RED before changing parser/chunker production code.
- [x] Convert Docling text/table items and their `prov` records into elements.
  Preserve exact page numbers, page sizes, bounding boxes, table indices, and
  parser version. Ignore malformed provenance instead of guessing.
- [x] Make pypdfium2 fallback emit one body element per page with page number and
  dimensions but no bbox/table coordinates.
- [x] Preserve element locators through overlap chunking, BM25 selection,
  deduplication, and `<source id="...">` formatting; run focused/full tests and
  commit as `feat: preserve PDF parser provenance`.

### Task 3: Bind extraction citations to validated source locations

**Files:**
- Modify: `autometa/agents/extraction_agent.py`
- Modify: `autometa/prompts/extraction.py`
- Modify: `autometa/services/workflow_operations.py`
- Modify: `tests/api/test_extraction_workflow.py`
- Create: `tests/agents/test_extraction_locators.py`

**Interfaces:**
- Extraction tool responses add optional `source_id` beside `citation`.
- `ExtractionAgent.run(..., file_ids: list[str] | None = None)` writes
  `FieldExtraction.source` only after deterministic validation.

- [x] Write failing tests for accepted source IDs, unique quotation fallback,
  rejected mismatches/ambiguity, file-ID association, researcher edits retaining
  the original locator, and no locator on `NOT FOUND`.
- [x] Verify RED with agent and extraction workflow tests.
- [x] Include stable source IDs in model context and function schemas. Map each
  output citation back to the exact chunks supplied for that file; never ask the
  model to invent page/table/bbox fields.
- [x] Store locators in the Sources artifact and provenance/audit export while
  keeping raw PDF text out of events.
- [x] Run focused/full backend tests and Ruff; commit as
  `feat: attach verified extraction sources`.

### Task 4: Serve Review-owned PDFs safely for local viewing

**Files:**
- Modify: `autometa/api/routers/files.py`
- Modify: `autometa/services/files.py`
- Modify: `autometa/schemas/files.py`
- Create: `tests/api/test_pdf_content.py`

**Interfaces:**
- Produces `GET /api/v1/reviews/{review_id}/files/{file_id}/content` with
  `application/pdf`, inline disposition, byte-range support, and private no-store
  caching.

- [ ] Write failing tests for Review ownership, PDF-only restriction, missing
  files, path traversal resistance, full response, valid/invalid byte ranges,
  content length/range headers, and absence of absolute paths.
- [ ] Verify RED before adding the endpoint.
- [ ] Resolve only through `FileStorage`, validate ownership/kind, and stream the
  validated file without loading the complete PDF into memory.
- [ ] Implement single-range `bytes=start-end` responses (`206`) and `416` for
  malformed/out-of-range requests so PDF.js can seek.
- [ ] Run focused/full tests and Ruff; commit as `feat: serve Review PDF content`.

### Task 5: Build the local PDF.js evidence reader

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/components/PdfEvidenceViewer.tsx`
- Create: `frontend/src/components/PdfEvidenceViewer.test.tsx`
- Create: `frontend/src/components/SourceEvidenceButton.tsx`
- Modify: `frontend/src/pages/ExtractionPage.tsx`
- Modify: `frontend/src/pages/ExtractionPage.test.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Bundles `pdfjs-dist` and worker locally.
- Opens evidence from each citation into a split reader with page, zoom, search,
  quotation, metadata, and optional bbox highlight.

- [ ] Add `pdfjs-dist` with the locked npm workflow; write failing tests with a
  mocked PDF.js document for page navigation, zoom, search, bbox conversion,
  page-only degradation, quotation-only notice, close/reopen, and no storage.
- [ ] Verify RED before adding viewer implementation.
- [ ] Render only the Review-owned content URL. Convert PDF bottom-left bbox to
  canvas top-left coordinates using the actual viewport transform and scale.
- [ ] Add evidence buttons to extraction rows. Show filename, page, element/table
  metadata, parser version, extraction type, derivation, and verbatim quotation.
- [ ] Run all frontend tests, typecheck, build twice, and commit source/compiled
  assets as `feat: add source-linked PDF reader`.

### Task 6: Phase 2C integration and visual/runtime gate

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-09-05-autometa-phase2c-pdf-evidence.md` only to check boxes and record verification.

**Interfaces:**
- Produces a locally mergeable Phase 2C branch and leaves expanded statistics as
  the final feature plan.

- [ ] Add an integration test that parses a generated two-page PDF, extracts from
  supplied fake model output, persists a locator, serves the PDF with range
  requests, and returns the locator in provenance/audit export.
- [ ] Document parser provenance, privacy disclosure, source-ID validation, PDF.js
  local assets, and the strict degradation policy.
- [ ] Run complete Python/frontend/Ruff/typecheck/deterministic-build/package gates
  and scan for PDF text or credentials in logs/events.
- [ ] Start Uvicorn with a temporary Review and generated PDF; browser-test bbox,
  page-only, and quotation-only modes at 1024/1280/1440/1920 and inspect rendered
  pages for clipping, overlap, highlight alignment, and console/network errors.
- [ ] Record results, verify no remote, commit, use verification and finishing
  skills, and merge locally without pushing.

## Completion Criteria

- Parser-provided page/table/bbox metadata survives into Sources artifacts.
- Every displayed locator is deterministically validated against supplied chunks.
- The UI highlights coordinates only when valid coordinates exist and follows the
  required page-only and quotation-only degradation language.
- PDF.js, worker, fonts, and application assets are local and reproducible.
- PDF byte serving is Review-scoped, range-capable, and path-safe.
- PDF contents and credentials never enter logs, events, provenance metadata, or
  browser storage.
