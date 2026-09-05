# AutoMeta Phase 2B Retrieval-Informed Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Search into a transparent seed-retrieval and query-expansion workflow that shows vocabulary changes, PubMed result-count changes, and optional known-study recall before final researcher approval.

**Architecture:** Keep one versioned `query` artifact as the complete Search strategy record. A durable `search.expand` operation generates a seed strategy, retrieves a bounded seed set, mines that real context through the existing SearchAgent, evaluates seed and expanded variants, and saves both forms plus a deterministic diff. The existing `search.run` operation continues to execute only the researcher-approved editable final query.

**Tech Stack:** FastAPI, Pydantic 2, existing PubMed integration and SearchAgent, SQLite provenance, React 18, TypeScript 5, TanStack Query, Vitest.

## Global Constraints

- Use only real PubMed responses and configured model output; never display benchmark or frozen manuscript data.
- Seed retrieval is bounded to 5–50 records and is always a durable server job.
- Optional known-study PMIDs are researcher inputs used only for transparent query evaluation; do not label them as benchmark recall.
- Preserve generated seed, generated expanded, and researcher-edited final queries separately.
- Show added/removed terms and count/known-study coverage changes; never claim recall when no known-study PMIDs were supplied.
- Approval applies to the current editable final query version only.
- Reruns use the Phase 2A registered-operation path and create new versions and provenance edges.
- PubMed keys and model credentials remain server-only; errors and events use the shared redactor.
- No automatic full-text download, example data, or unsupported precision/recall claims.
- Use TDD, run complete gates, commit locally, and never push.

---

### Task 1: Define retrieval-feedback schemas and deterministic query diffs

**Files:**
- Modify: `autometa/schemas/models.py`
- Modify: `autometa/schemas/workflows.py`
- Create: `autometa/search/query_diff.py`
- Create: `autometa/search/__init__.py`
- Create: `tests/services/test_query_diff.py`

**Interfaces:**
- Produces `SearchExpansionRequest(seed_retmax, included_pmids, min_year, max_year)`.
- Produces `SearchStrategySnapshot`, `SearchStrategyComparison`, and
  `diff_queries(seed: str, expanded: str) -> SearchStrategyComparison`.

- [x] Write failing tests for stable term extraction, field-tag preservation,
  added/removed term order, identical queries, empty queries, and PMID trimming/
  deduplication.
- [x] Run `.venv/bin/python -m pytest tests/services/test_query_diff.py -q`
  and verify RED because the schemas and diff function do not exist.
- [x] Implement a parser that compares normalized quoted phrases and PubMed
  field-tagged terms without rewriting the executable query.
- [x] Validate years as in `SearchRunWorkflowRequest`; normalize PMIDs to unique
  nonempty strings while preserving first-seen order.
- [x] Run focused tests and Ruff; commit as
  `feat: define retrieval feedback contracts`.

### Task 2: Add a bounded seed and expansion operation to SearchAgent

**Files:**
- Modify: `autometa/agents/search_agent.py`
- Modify: `autometa/schemas/models.py`
- Create: `tests/agents/test_search_expansion.py`

**Interfaces:**
- Produces:

```python
SearchAgent.expand_with_retrieval_feedback(
    pico: PICODefinition,
    *,
    seed_retmax: int,
    included_pmids: list[str],
    min_year: int | None,
    max_year: int | None,
) -> SearchExpansionResult
```

- [ ] Write failing tests with fake PubMed/LLM collaborators for call order,
  seed bounds, real seed citation context, three variant evaluations, optional
  known-study coverage, and provider failure propagation.
- [ ] Verify RED with
  `.venv/bin/python -m pytest tests/agents/test_search_expansion.py -q`.
- [ ] Generate the seed strategy from PICO, retrieve only the balanced seed query,
  format titles/abstracts/indexed terms as bounded expansion context, generate an
  expanded strategy, and evaluate both strategies through existing count APIs.
- [ ] Return seed records only as structured source metadata needed for review;
  do not persist or log credentials, request headers, or benchmark labels.
- [ ] Run focused/full backend tests and Ruff; commit as
  `feat: add retrieval informed query expansion`.

### Task 3: Add the durable Search expansion API and provenance

**Files:**
- Modify: `autometa/services/workflow_operations.py`
- Modify: `autometa/api/routers/workflows.py`
- Modify: `frontend/src/api/workflows.ts`
- Create: `tests/api/test_search_expansion_workflow.py`
- Modify: `tests/services/test_reruns.py`

**Interfaces:**
- Produces `POST /api/v1/reviews/{review_id}/workflow/search/expand`.
- Registers `search.expand` in `WorkflowOperationRegistry`.
- Saves a draft `query` payload with keys `seed`, `expanded`, `comparison`,
  `included_pmids`, `generated_raw_query`, and `raw_query`.

- [ ] Write failing API tests for approved-PICO gating, immediate Job response,
  seed/result persistence, count and coverage fields, safe failure, concurrent
  Search conflict, and rerun from the completed provenance event.
- [ ] Verify RED with the focused API/rerun tests.
- [ ] Implement the registered operation and route. Persist the request and exact
  PICO version through the Phase 2A coordinator and save the Query with agent
  provenance context.
- [ ] Keep `search.query` for a fast no-retrieval draft; `search.expand` is an
  explicit researcher choice and never runs implicitly.
- [ ] Run complete backend tests and Ruff; commit as
  `feat: add durable retrieval feedback workflow`.

### Task 4: Build the query comparison and feedback UI

**Files:**
- Create: `frontend/src/components/SearchStrategyComparison.tsx`
- Modify: `frontend/src/pages/SearchPage.tsx`
- Modify: `frontend/src/pages/SearchPage.test.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Adds `Generate with retrieval feedback` alongside the existing fast generation
  action.
- Renders seed and expanded variants, result counts, optional known-study hits,
  added/removed terms, warnings, and the editable final query.

- [ ] Write failing React tests for seed limits, optional PMID input, loading and
  failure states, no false recall label, query/count diffs, editable final query,
  approval invalidation, and disabled execution before approval.
- [ ] Run the focused Vitest file and verify RED.
- [ ] Implement the comparison component with text/glyph semantics in addition to
  color and horizontally scrollable query text at 1024 px.
- [ ] Keep every displayed metric sourced from the saved Query artifact; do not
  calculate or invent values in the browser.
- [ ] Run the full frontend suite, typecheck, build, and deterministic rebuild;
  commit source and compiled assets as `feat: add Search feedback workspace`.

### Task 5: Phase 2B integration and runtime gate

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-09-05-autometa-phase2b-retrieval-feedback.md` only to check boxes and record verification.

**Interfaces:**
- Produces a locally mergeable Phase 2B branch and leaves PDF evidence navigation
  and expanded statistics for their dedicated plans.

- [ ] Add an integration test proving seed and expanded strategies are versioned,
  an approved edited final query is the only query executed, and rerun lineage
  points to the exact historical PICO version.
- [ ] Document fast generation versus retrieval-informed generation, PubMed network
  requirements, known-study coverage semantics, and privacy boundaries.
- [ ] Run all Python tests, Ruff, all frontend tests, typecheck, two deterministic
  builds, production-content scans, and package build/install smoke tests.
- [ ] Start Uvicorn with temporary data and browser-test both generation choices,
  comparison rendering, edit/approve flow, and 1024/1280/1440/1920 layouts using
  controlled fake HTTP dependencies where external credentials are unavailable.
- [ ] Record exact results, verify no remote is configured, commit locally, use
  `verification-before-completion`, and merge locally with
  `finishing-a-development-branch`. Never push.

## Completion Criteria

- Search can explicitly run a real bounded seed retrieval before expansion.
- Seed and expanded strategies, their PubMed counts, optional known-study hits,
  and deterministic term changes are persisted in the Query artifact.
- The final editable raw query is distinct from generated forms and is the only
  query consumed by final PubMed retrieval after approval.
- `search.expand` participates in provenance, audit export, and safe historical
  rerun using the exact PICO version and request.
- The UI shows no benchmark language, fabricated metric, credential, or enabled
  dead control, and remains usable at all supported widths.
