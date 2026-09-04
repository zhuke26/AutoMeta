# AutoMeta Phase 1D Real Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all guarded React stage placeholders with real, Review-scoped, persistent Setup, Search, Screening, Extraction, and Meta-analysis workflows backed by durable jobs and versioned artifacts.

**Architecture:** Keep the existing agent implementations as domain engines, but invoke every long-running operation through a new `WorkflowCoordinator` and the persistent `JobManager`. Inputs are saved as Review artifacts or Review-owned files before a job starts; outputs are saved as draft artifacts from the worker thread. The React pages use typed `/api/v1/reviews/:id/workflow/*` contracts, reconnect to the latest persisted job, autosave editable drafts, and require explicit artifact approval before downstream work.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy/SQLite, in-process `ThreadPoolExecutor`, React 18, TypeScript 5, TanStack Query 5, React Router 7, Vitest, Testing Library.

## Global Constraints

- Product UI is English-only and contains no manuscript, benchmark, or example data.
- API keys remain in `.env` and server memory and never enter requests, SQLite, job events, or frontend state.
- All long-running model, PubMed, parsing, extraction, and analysis work is owned by the server job manager, not an SSE connection.
- Editing an approved artifact revokes that approval and marks downstream artifacts stale through the existing artifact service.
- Every downstream run requires the exact approved upstream artifact kinds documented below; a missing, draft, or stale input produces a clear `409` response.
- A failed validation or model/statistical operation stops and reports the error; no method, effect measure, estimator, or model is silently substituted.
- Extraction sends PDF text to the configured model service only after the locally persisted disclosure acknowledgement is true.
- Manual PDF and CSV upload only; no automatic publisher or full-text download.
- Compiled frontend assets remain committed and reproducible.
- Continue on `codex/phase1c-react-library`; do not merge until Task 9 passes, and never push a remote.

---

### Task 1: Add Review-scoped job discovery and workflow coordination

**Files:**
- Create: `autometa/repositories/stage_runs.py`
- Create: `autometa/services/workflows.py`
- Create: `autometa/schemas/workflows.py`
- Create: `autometa/api/routers/workflows.py`
- Create: `tests/services/test_workflow_coordinator.py`
- Create: `tests/api/test_workflow_jobs.py`
- Modify: `autometa/repositories/jobs.py`
- Modify: `autometa/api/routers/jobs.py`
- Modify: `autometa/api/dependencies.py`
- Modify: `autometa/api/main.py`

**Interfaces:**
- Produces `GET /api/v1/reviews/{review_id}/jobs?stage=<stage>&limit=20` returning newest-first `JobView[]`.
- Produces `WorkflowCoordinator.submit(review_id, stage, input_artifacts, operation) -> JobView`.
- Persists one `StageRun` per submitted job with immutable `input_artifact_ids` and mirrors terminal job state into `StageRun.status`.
- Maps `JobConflict` to HTTP 409 and missing Reviews to HTTP 404.

- [ ] Write repository tests proving newest-first job listing, stage filtering, and Review isolation.
- [ ] Run `pytest tests/api/test_workflow_jobs.py tests/services/test_workflow_coordinator.py -q` and verify failures because the repository and coordinator do not exist.
- [ ] Implement these concrete coordinator methods:

```python
class WorkflowCoordinator:
    def require_approved(self, review_id: str, kinds: tuple[str, ...]) -> list[ArtifactView]: ...
    def submit(
        self,
        review_id: str,
        stage: str,
        input_artifacts: list[ArtifactView],
        operation: Callable[[JobContext], dict | None],
    ) -> JobView: ...
```

- [ ] Add `JobRepository.list_for_review(review_id, stage=None, limit=20)` and the Review-scoped GET endpoint.
- [ ] On submission create a `StageRun(status="queued")`; on job transitions update it to `running`, `succeeded`, `failed`, `interrupted`, or `cancelled` without storing secrets.
- [ ] Add API tests for 404, 409, filtering, terminal results, and interrupted jobs visible after app restart.
- [ ] Run the focused tests and the complete Python suite.
- [ ] Commit as `feat: add Review workflow coordination`.

### Task 2: Add typed artifact, approval, file, and durable-job frontend infrastructure

**Files:**
- Create: `frontend/src/api/artifacts.ts`
- Create: `frontend/src/api/files.ts`
- Create: `frontend/src/api/jobs.ts`
- Create: `frontend/src/api/workflows.ts`
- Create: `frontend/src/hooks/useAutosavedArtifact.ts`
- Create: `frontend/src/hooks/useDurableJob.ts`
- Create: `frontend/src/components/ArtifactApprovalBar.tsx`
- Create: `frontend/src/components/JobProgressPanel.tsx`
- Create: `frontend/src/components/ArtifactApprovalBar.test.tsx`
- Create: `frontend/src/hooks/useDurableJob.test.tsx`
- Modify: `frontend/src/api/types.ts`

**Interfaces:**
- Produces `saveArtifact`, `approveArtifact`, `revokeArtifact`, `uploadReviewFiles`, `listReviewFiles`, `listReviewJobs`, and stage-start functions.
- `useAutosavedArtifact(reviewId, kind, payload, enabled)` debounces for 600 ms, displays saving/saved/error state, and invalidates current artifact queries.
- `useDurableJob(reviewId, stage)` finds the newest persisted job, polls while queued/running, reconnects with `EventSource` using the last sequence, and exposes retry-ready interrupted/failed state.

- [ ] Write failing hook/component tests for debounce, approval, stale rejection, SSE replay, browser disconnect, polling fallback, interrupted state, and server errors.
- [ ] Implement exact artifact request bodies already accepted by the API:

```ts
type SaveArtifactInput = { payload: Record<string, unknown> };
type ApproveArtifactInput = { artifact_id: string; version: number };
```

- [ ] Implement `JobProgressPanel` so queued/running/interrupted/failed/succeeded are text-labelled; never infer success from a closed SSE stream.
- [ ] Ensure no browser storage or request includes API credentials.
- [ ] Run focused tests, the full frontend suite, typecheck, and build.
- [ ] Commit as `feat: add durable workflow client infrastructure`.

### Task 3: Implement persisted Review Setup and PICO approval

**Files:**
- Modify: `autometa/schemas/workflows.py`
- Modify: `autometa/services/workflows.py`
- Modify: `autometa/api/routers/workflows.py`
- Create: `tests/api/test_protocol_workflow.py`
- Create: `frontend/src/pages/ReviewSetupPage.test.tsx`
- Modify: `frontend/src/pages/ReviewSetupPage.tsx`

**Interfaces:**
- `POST /api/v1/reviews/{review_id}/workflow/protocol/draft` accepts `{research_question}` and returns `JobView` immediately.
- The worker calls `ProtocolAgent.run`, emits `drafting` and `artifact_saved`, and saves `question_pico` as:

```json
{
  "research_question": "string",
  "pico": {"P": "", "I": "", "C": "", "O": ""},
  "recommended_outcomes": [],
  "rationale": "string"
}
```

- [ ] Write failing API tests with a fake `ProtocolAgent` proving immediate job return, continued execution without SSE, saved draft, safe failure, and 409 on concurrent protocol jobs.
- [ ] Implement the Review-scoped protocol job and save its output through `ArtifactService.save_draft`.
- [ ] Write failing React tests for manual PICO entry, draft generation, restored progress, field editing, 600 ms autosave, and Approve enabling the Search route.
- [ ] Replace the Setup placeholder with the research-question form and four explicit P/I/C/O fields. For independent entry modes, allow direct PICO entry without model generation.
- [ ] Require nonempty P, I, and O before approval; C may explicitly say `No comparator specified`.
- [ ] Run backend/frontend focused tests and full typecheck/build.
- [ ] Commit as `feat: add persisted PICO Review setup`.

### Task 4: Implement Search query approval, PubMed retrieval, records, and exports

**Files:**
- Modify: `autometa/schemas/workflows.py`
- Modify: `autometa/services/workflows.py`
- Modify: `autometa/api/routers/workflows.py`
- Create: `tests/api/test_search_workflow.py`
- Create: `frontend/src/pages/SearchPage.tsx`
- Create: `frontend/src/pages/SearchPage.test.tsx`
- Create: `frontend/src/components/RecordsTable.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- `POST .../workflow/search/query` requires approved `question_pico`, calls `SearchAgent.generate_field_tagged_strategy`, and saves draft `query` with generated and editable raw-query fields.
- `POST .../workflow/search/run` requires approved `query`, accepts `{retmax, fetch_all, min_year, max_year}`, runs PubMed in a durable job, and saves draft `records` containing real `query_url`, counts, and paper rows.
- Search records export downloads the current artifact as JSON, CSV, or RIS without rerunning PubMed.

- [ ] Write failing API tests using a fake SearchAgent for upstream approval enforcement, empty-query rejection, job events, records persistence, and PubMed errors.
- [ ] Implement the two job operations with exact input artifact IDs recorded in `StageRun`.
- [ ] Write failing React tests for query generation, raw-query editing/autosave, approval gate, retrieval settings, job reconnection, record search/sort/pagination, and JSON/CSV/RIS exports.
- [ ] Implement the real Search page; disabled controls remain disabled until their required artifact is approved.
- [ ] Approve Records explicitly before Screening can consume them.
- [ ] Run focused and complete suites, typecheck, and build.
- [ ] Commit as `feat: migrate the Search workflow`.

### Task 5: Implement Screening import, durable ranking, human selection, and approval

**Files:**
- Modify: `autometa/schemas/workflows.py`
- Modify: `autometa/services/workflows.py`
- Modify: `autometa/api/routers/workflows.py`
- Create: `tests/api/test_screening_workflow.py`
- Create: `frontend/src/pages/ScreeningPage.tsx`
- Create: `frontend/src/pages/ScreeningPage.test.tsx`
- Create: `frontend/src/components/ScreeningTable.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- `PUT .../workflow/screening/records` validates imported JSON/CSV rows as `PaperInput[]` and saves draft `records` for independent Screening Reviews.
- `POST .../workflow/screening/run` requires approved `question_pico` and `records`, accepts `{study_design_filter, max_concurrency}`, calls `ScreeningAgentV2.run_scored_direct`, and saves draft `selected_studies` containing decisions plus explicit `selected_pmids`.

- [ ] Write failing API tests for JSON/CSV validation, approved-input enforcement, dimension evidence preservation, durable progress, error stop, and draft output.
- [ ] Implement import and job routes without using the legacy connection-owned streaming endpoint.
- [ ] Write failing React tests for independent import, P/I/C/O columns, evidence text, score/confidence sorting, filters, Top N, bulk/manual selection, uncertain retention, autosave, and approval.
- [ ] Implement the Screening page with real persisted decisions and selected IDs; do not imply automatic exclusion.
- [ ] Run focused and complete suites, typecheck, and build.
- [ ] Commit as `feat: migrate the Screening workflow`.

### Task 6: Generalize Review-owned uploads and implement Extraction disclosure and workflow

**Files:**
- Create: `migrations/versions/0002_file_kinds.py`
- Modify: `autometa/persistence/models.py`
- Modify: `autometa/schemas/files.py`
- Modify: `autometa/services/files.py`
- Modify: `autometa/api/routers/files.py`
- Modify: `autometa/schemas/workflows.py`
- Modify: `autometa/services/workflows.py`
- Modify: `autometa/api/routers/workflows.py`
- Create: `tests/api/test_extraction_workflow.py`
- Create: `frontend/src/pages/ExtractionPage.tsx`
- Create: `frontend/src/pages/ExtractionPage.test.tsx`
- Create: `frontend/src/components/PdfUploadPanel.tsx`
- Create: `frontend/src/components/ExtractionTable.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- `FileRecord.kind` is `pdf | csv`; PDFs remain under `uploads/`, CSVs under `datasets/`; MIME, extension, signature/content, size, path traversal, ownership, and duplicate hashes are validated.
- `POST .../workflow/extraction/run` accepts `{file_ids, study_characteristics_fields, study_results_fields, top_k, max_concurrency}` and requires the local setting `pdf_model_disclosure_acknowledged=true`.
- The worker resolves Review-owned PDF paths, emits parser/extraction events, calls `ExtractionAgent.run`, and saves draft `sources` with editable values, confidence, filename, outcome, verbatim citation, and `researcher_edited` flags.

- [ ] Write migration/storage tests for PDF compatibility, CSV separation, ownership, invalid signatures, duplicate files, and Review deletion.
- [ ] Write failing workflow tests for acknowledgement gating, no upstream-selected-studies requirement in extraction-only mode, durable execution, citation preservation, and failures.
- [ ] Write failing React tests for first-run disclosure, manual PDF upload, file restoration, field definitions, job progress, editable results, researcher-edit markers, selected meta-analysis rows, CSV/JSON export, and approval.
- [ ] Implement the disclosure acknowledgement through a nonsecret local setting API; never place file text or credentials in job events.
- [ ] Replace the Extraction placeholder and run all focused/full gates.
- [ ] Commit as `feat: migrate the Extraction workflow`.

### Task 7: Implement CSV datasets, method-plan approval, and deterministic Meta-analysis execution

**Files:**
- Modify: `autometa/schemas/workflows.py`
- Modify: `autometa/services/workflows.py`
- Modify: `autometa/api/routers/workflows.py`
- Create: `tests/api/test_meta_analysis_workflow.py`
- Create: `frontend/src/pages/MetaAnalysisPage.tsx`
- Create: `frontend/src/pages/MetaAnalysisPage.test.tsx`
- Create: `frontend/src/components/MetaPlanEditor.tsx`
- Create: `frontend/src/components/MetaResultsPanel.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- `POST .../workflow/meta/plan` accepts `{file_ids, user_hint, sample_rows, max_concurrency}`, reads Review-owned CSVs, calls `MetaAnalysisPlannerAgent`, and saves draft `plan`.
- `POST .../workflow/meta/run` requires approved `plan`, validates every referenced CSV and mapping before starting, calls `MetaAnalysisRunnerAgent`, and saves draft `code` and `result` artifacts atomically.
- No fallback changes effect measure, effect source, pooling model, fixed method, random estimator, or continuity correction.

- [ ] Write failing API tests for Review file ownership, invalid CSV, plan persistence, approval gate, strict validation failure, generated code/result persistence, and no silent method substitution.
- [ ] Write failing React tests for CSV upload, summaries, editable structured plan fields, assumptions/warnings, approval, failed-run errors, pooled effect, confidence interval, Q/I²/tau², study effects, weights, logs, code, and exports.
- [ ] Implement the Meta-analysis page with no fabricated forest plot; render only outputs returned by the validated engine.
- [ ] Run focused/full suites, typecheck, build, and deterministic calculation fixtures already supported by the current runner.
- [ ] Commit as `feat: migrate the Meta-analysis workflow`.

### Task 8: Remove placeholders and verify end-to-end approval/invalidation behavior

**Files:**
- Delete: `frontend/src/pages/StagePendingPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/ReviewWorkspace.tsx`
- Create: `tests/api/test_guided_review_flow.py`
- Create: `frontend/src/pages/GuidedReviewFlow.test.tsx`

**Interfaces:**
- Guided route chain is Setup → Search → Screening → Extraction → Meta-analysis.
- Independent routes begin at their selected stage and can proceed downstream once their real output is approved.

- [ ] Write a backend integration test that uses fake agents to run all stages, edits an approved upstream artifact, and proves downstream artifacts become stale and cannot be consumed.
- [ ] Write a frontend integration test that resumes an interrupted job, approves each artifact, navigates downstream, and never exposes an enabled dead control.
- [ ] Replace every pending route with the real page and remove placeholder copy from production assets.
- [ ] Search source and compiled output for `Workflow migration pending`, `Stage unavailable`, `Load Example`, benchmark identifiers, and legacy product naming; require no production hits.
- [ ] Run complete frontend/backend suites, typecheck, audit, and build.
- [ ] Commit as `feat: complete the four-stage React workflow`.

### Task 9: Real-runtime and branch integration gate

**Files:**
- Modify: `README.md`
- Modify: `.github/workflows/foundation.yml`
- Modify: `docs/superpowers/plans/2026-09-05-autometa-phase1d-real-workflows.md` only to check completed boxes and record exact verification commands.

**Interfaces:**
- Produces a Phase 1D branch that is safe to merge locally into `main` while retaining Phase 2 as the next roadmap stage.

- [ ] Document stage prerequisites, approval semantics, browser-close behavior, interrupted retry, PDF disclosure, and manual file support.
- [ ] Run `npm ci`, frontend tests, typecheck, build, and confirm a second clean build produces no `autometa/static` diff.
- [ ] Run the complete Python suite, Ruff, wheel/sdist build, wheel-content inspection, and a clean virtual-environment smoke install.
- [ ] Start real Uvicorn with a temporary data directory and browser-test Guided plus each independent entry path at 1024, 1280, 1440, and 1920 px.
- [ ] Verify no console errors, remote font/CDN requests, API key/browser storage, fabricated results, benchmark content, or enabled dead controls.
- [ ] Confirm `git remote -v` is empty and all changes are committed locally.
- [ ] Use `verification-before-completion`, then `finishing-a-development-branch`; merge locally into `main` only after all checks pass, never push.
