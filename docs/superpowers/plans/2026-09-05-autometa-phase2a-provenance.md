# AutoMeta Phase 2A Provenance and Rerun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an immutable, Review-scoped provenance timeline with artifact history and diffs, approval/edit attribution, reproducible stage reruns, and a portable JSON audit export.

**Architecture:** Extend the existing SQLite artifact/version foundation with append-only Review events, researcher-edit records, provenance edges, and rerun relationships. Refactor durable workflow closures behind a registered operation interface so an eligible completed event can be replayed from its exact persisted request and input artifact versions without overwriting history. Expose the graph through versioned FastAPI contracts and a React provenance workspace opened from the existing bottom rail.

**Tech Stack:** Python 3.11/3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, SQLite, React 18, TypeScript 5, TanStack Query 5, React Router 7, Vitest, Testing Library.

## Global Constraints

- Preserve local, single-user deployment and the current `/api/v1` boundary.
- Provenance records are append-only; corrections, revocations, failures, and reruns create new records and never rewrite historical records.
- Persist exact artifact version IDs at workflow boundaries, not only mutable artifact IDs.
- Persist no API key, authorization header, PDF text, CSV contents, or absolute local path in events, stage requests, exports, logs, or frontend state.
- Provider metadata may contain only the sanitized endpoint origin and resolved model name.
- Only successfully completed, registered workflow operations are rerunnable.
- A rerun uses the source run's immutable request payload and input artifact versions and creates a new job, stage run, output versions, provenance edges, and rerun relationship.
- Existing approval, stale propagation, browser-disconnection behavior, and stage functionality remain unchanged.
- Audit export includes Review metadata, file metadata, artifact versions, approvals, events, stage runs, graph edges, edits, and rerun relationships, but never file contents or credentials.
- Product UI remains English-only, contains no manuscript/benchmark/example data, and supports widths of 1024 px and above.
- Use test-first implementation. Every task ends with focused tests, the complete Python or frontend suite, Ruff/typecheck/build as applicable, and a local commit. Never push.

---

### Task 1: Add the append-only provenance schema and migration

**Files:**
- Create: `migrations/versions/0002_provenance.py`
- Modify: `autometa/persistence/models.py`
- Create: `tests/persistence/test_provenance_schema.py`
- Create: `tests/persistence/test_migrations.py`

**Interfaces:**
- Produces: `ReviewEvent`, `ResearcherEdit`, `ProvenanceEdge`, and `RerunRelationship` ORM models.
- Extends: `StageRun.operation_kind`, `StageRun.request_payload`, `StageRun.input_artifact_version_ids`, and `StageRun.output_artifact_version_ids`.

- [x] **Step 1: Write failing schema tests**

Assert that a fresh database contains `review_events`, `researcher_edits`,
`provenance_edges`, and `rerun_relationships`; that every table cascades with
Review deletion; and that `(review_id, sequence)`, provenance edge identity,
and rerun target uniqueness are enforced.

```python
def test_provenance_rows_are_review_scoped_and_append_only(database, review) -> None:
    event = ReviewEvent(
        review_id=review.id,
        sequence=1,
        stage="search",
        event_type="artifact.version_created",
        producer="agent",
        payload={"model": "test-model"},
    )
    with database.session() as session:
        session.add(event)
    with pytest.raises(IntegrityError):
        with database.session() as session:
            session.add(ReviewEvent(
                review_id=review.id,
                sequence=1,
                event_type="duplicate",
                producer="system",
                payload={},
            ))
```

- [x] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/persistence/test_provenance_schema.py tests/persistence/test_migrations.py -q`

Expected: failure because migration `0002` and the four ORM models do not exist.

- [x] **Step 3: Implement migration `0002` and matching ORM models**

Use these persisted fields:

```text
review_events:
  id, review_id, sequence, stage?, event_type, producer,
  stage_run_id?, job_id?, artifact_version_id?, elapsed_ms?, payload, created_at
researcher_edits:
  id, review_id, artifact_id, from_version_id?, to_version_id,
  changed_paths, created_at
provenance_edges:
  id, review_id, source_version_id, target_version_id, relation, created_at
rerun_relationships:
  id, review_id, source_stage_run_id, rerun_stage_run_id,
  source_event_id, created_at
stage_runs additions:
  operation_kind?, request_payload, input_artifact_version_ids,
  output_artifact_version_ids
```

Use `ondelete="CASCADE"` for Review-owned records and version-owned edit/edge
records, `ondelete="SET NULL"` only for optional job/stage-run references, and
JSON defaults of `{}` or `[]` rather than nullable request or graph fields.
Existing Phase 1 `stage_runs` receive empty version/output lists and a null
operation kind; they remain visible in history but are explicitly non-rerunnable.

- [x] **Step 4: Verify migration upgrade and model parity**

Run:

```bash
.venv/bin/python -m pytest tests/persistence/test_provenance_schema.py tests/persistence/test_migrations.py -q
.venv/bin/ruff check autometa/persistence migrations tests/persistence
```

Expected: focused tests pass and model/migration column names match exactly.

- [x] **Step 5: Commit the schema**

```bash
git add autometa/persistence/models.py migrations/versions/0002_provenance.py tests/persistence
git diff --cached --check
git commit -m "feat: add provenance persistence schema"
```

### Task 2: Implement the provenance ledger and safe metadata boundary

**Files:**
- Create: `autometa/security/__init__.py`
- Create: `autometa/security/redaction.py`
- Create: `autometa/repositories/provenance.py`
- Create: `autometa/services/provenance.py`
- Create: `autometa/schemas/provenance.py`
- Create: `tests/services/test_provenance.py`
- Modify: `autometa/jobs/manager.py`

**Interfaces:**
- Produces: `ProvenanceService.record(...) -> ReviewEventView`, `list_events(...)`, `graph(...)`, and `safe_metadata(...)`.
- Produces: `Producer = researcher | agent | system` and typed event/edge/edit/rerun views.
- Consumes: `Settings` only inside the server-side redactor.

- [x] **Step 1: Write failing ledger and redaction tests**

Cover monotonic per-Review sequence numbers, Review isolation, stable
newest/oldest pagination, all foreign-key ownership checks, concurrent event
writes, and recursive redaction of configured secret values and secret-shaped
keys.

```python
def test_event_payload_never_persists_credentials(provenance, settings, review) -> None:
    event = provenance.record(
        review.id,
        event_type="stage.started",
        producer="agent",
        payload={"api_key": "value", "nested": {"token": "value"}},
    )
    assert event.payload == {
        "api_key": "[REDACTED]",
        "nested": {"token": "[REDACTED]"},
    }
```

- [x] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m pytest tests/services/test_provenance.py -q`

Expected: import failure because the provenance repository/service do not exist.

- [x] **Step 3: Implement one shared recursive redactor**

Move the existing JobManager secret-value replacement behind:

```python
class SecretRedactor:
    def __init__(self, settings: Settings): ...
    def text(self, value: str) -> str: ...
    def payload(self, value: object) -> object: ...
```

Redact configured secret values and keys matching `api_key`, `authorization`,
`cookie`, `password`, `secret`, or `token` case-insensitively. Reuse this class
for job events/errors and provenance payloads so the two stores cannot diverge.

- [x] **Step 4: Implement repository/service ordering and ownership checks**

`record()` allocates `sequence = max(sequence) + 1` in the same SQLite write
transaction and retries once on a unique-sequence collision. All referenced
artifact versions, jobs, and stage runs must belong to the same Review.

- [x] **Step 5: Verify GREEN and commit**

Run:

```bash
.venv/bin/python -m pytest tests/services/test_provenance.py tests/jobs -q
.venv/bin/ruff check autometa/security autometa/repositories/provenance.py autometa/services/provenance.py autometa/schemas/provenance.py autometa/jobs
```

Then commit as `feat: add append-only provenance ledger`.

### Task 3: Record artifact versions, researcher edits, approvals, and stale propagation

**Files:**
- Modify: `autometa/schemas/artifacts.py`
- Modify: `autometa/repositories/artifacts.py`
- Modify: `autometa/services/artifacts.py`
- Modify: `autometa/api/routers/artifacts.py`
- Create: `autometa/provenance/diff.py`
- Create: `autometa/provenance/__init__.py`
- Create: `tests/services/test_artifact_history.py`
- Create: `tests/api/test_artifact_history.py`

**Interfaces:**
- Extends: `ArtifactView.version_id: str`.
- Produces: `ArtifactWriteContext(producer, stage_run_id, job_id, input_version_ids, metadata)`.
- Produces: `ArtifactVersionView`, `ArtifactDiffView`, `list_versions()`, `get_version()`, and `diff_versions()`.
- Produces endpoints:
  - `GET /api/v1/reviews/{review_id}/artifacts/{kind}/versions`
  - `GET /api/v1/reviews/{review_id}/artifacts/{kind}/versions/{version}`
  - `GET /api/v1/reviews/{review_id}/artifacts/{kind}/diff?from_version=1&to_version=2`

- [ ] **Step 1: Write failing history and diff tests**

Require immutable version payloads, exact version IDs, current/noncurrent
approval visibility, cross-Review rejection, deterministic JSON-pointer diffs,
researcher-edit changed paths, explicit revoke events, and one stale event per
downstream artifact.

`ArtifactVersionView` must expose `version_id`, `version`, `payload`,
`content_hash`, `created_at`, `approval_status`, `approved_at`, and `revoked_at`.

```python
def test_researcher_edit_creates_diff_and_stale_events(artifact_service, review) -> None:
    first = artifact_service.save_draft(review.id, "query", {"raw_query": "A"})
    artifact_service.approve(review.id, first.artifact_id, first.version)
    second = artifact_service.save_draft(review.id, "query", {"raw_query": "A AND B"})
    diff = artifact_service.diff_versions(review.id, "query", 1, 2)
    assert diff.changes == [{
        "op": "replace",
        "path": "/raw_query",
        "before": "A",
        "after": "A AND B",
    }]
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/services/test_artifact_history.py tests/api/test_artifact_history.py -q`

- [ ] **Step 3: Implement deterministic recursive JSON diffing**

Emit sorted `add`, `remove`, and `replace` changes. Escape JSON Pointer `~` and
`/`; treat list replacement as one value-level change so reordered scientific
rows are not misrepresented as many unrelated edits.

- [ ] **Step 4: Make artifact lifecycle and provenance atomic**

Within the same database transaction as each version/approval change:

- record `artifact.version_created`, `artifact.approved`, `artifact.revoked`,
  and `artifact.stale` events;
- create `ResearcherEdit` only when producer is `researcher` and a prior version
  exists;
- create provenance edges from every declared input version to each output
  version;
- mark downstream StageRuns `stale` together with their artifacts and record the
  affected StageRun IDs in the stale event payload;
- keep existing public methods source-compatible by using a researcher context
  when no explicit context is passed.

- [ ] **Step 5: Add version and diff APIs, verify, and commit**

Run:

```bash
.venv/bin/python -m pytest tests/services/test_artifacts.py tests/services/test_artifact_history.py tests/api/test_artifact_history.py -q
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check .
```

Commit as `feat: add immutable artifact history and diffs`.

### Task 4: Persist reproducible workflow run descriptors and provenance edges

**Files:**
- Modify: `autometa/repositories/stage_runs.py`
- Modify: `autometa/services/workflows.py`
- Modify: `autometa/api/dependencies.py`
- Modify: `autometa/api/routers/workflows.py`
- Modify: `autometa/schemas/jobs.py`
- Modify: `autometa/config.py`
- Create: `tests/services/test_workflow_provenance.py`
- Modify: `tests/api/test_protocol_workflow.py`
- Modify: `tests/api/test_search_workflow.py`
- Modify: `tests/api/test_screening_workflow.py`
- Modify: `tests/api/test_extraction_workflow.py`
- Modify: `tests/api/test_meta_analysis_workflow.py`

**Interfaces:**
- Replaces coordinator submission with:

```python
coordinator.submit(
    review_id=review_id,
    stage="search",
    operation_kind="search.run",
    request_payload=request.model_dump(mode="json"),
    input_artifacts=inputs,
    operation=operation,
)
```

- Adds `JobContext.stage_run_id`, `JobContext.artifact_context(...)`, and
  `StageRunView` fields for request, exact inputs, exact outputs, and duration.

- [ ] **Step 1: Write failing coordinator tests**

Assert that requests are persisted after secret redaction, exact input version
IDs are stored, output version IDs are attached on success, failures create a
`stage.failed` event, and model metadata contains only sanitized provider origin,
resolved model, application version, and operation kind.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/services/test_workflow_provenance.py -q`

- [ ] **Step 3: Extend coordinator/job context and update all workflow routes**

Every agent-generated `save_draft` or `save_drafts` call must use the context
returned by `JobContext.artifact_context(producer="agent", metadata=...)`.
Every workflow route must persist its Pydantic request using JSON mode. Do not
store PDF/CSV bytes, parsed PDF text, PubMed abstracts, or credentials in the
request or metadata fields.

- [ ] **Step 4: Verify exact graph edges and failure events**

Run all five workflow API test modules and assert each successful output version
has edges from the exact input version IDs recorded on its StageRun.

- [ ] **Step 5: Run the full backend gate and commit**

Run `.venv/bin/python -m pytest tests -q && .venv/bin/ruff check .` and commit as
`feat: capture workflow provenance`.

### Task 5: Register workflow operations and implement safe event reruns

**Files:**
- Create: `autometa/services/workflow_operations.py`
- Create: `autometa/services/reruns.py`
- Modify: `autometa/services/workflows.py`
- Modify: `autometa/api/dependencies.py`
- Modify: `autometa/api/routers/workflows.py`
- Create: `tests/services/test_reruns.py`
- Create: `tests/api/test_reruns.py`

**Interfaces:**
- Produces: `WorkflowOperationRegistry.execute(operation_kind, execution) -> dict`.
- Produces: `RerunService.rerun(review_id, source_event_id) -> JobView`.
- Produces: `POST /api/v1/reviews/{review_id}/provenance/events/{event_id}/rerun`.
- Registered operations: `protocol.draft`, `search.query`, `search.run`,
  `screening.run`, `extraction.run`, `meta.plan`, and `meta.run`.

- [ ] **Step 1: Write failing registry and rerun tests**

Cover operation allowlisting, Review ownership, completed-event requirement,
exact historical input-version loading, missing file rejection, concurrent-stage
conflict, creation of a new StageRun/job, output version increments, provenance
edges, and `RerunRelationship` linkage.

```python
def test_rerun_replays_exact_historical_inputs(reruns, completed_event) -> None:
    job = reruns.rerun(completed_event.review_id, completed_event.id)
    terminal = wait_for_terminal(job.id)
    relation = reruns.relationship_for_job(terminal.id)
    assert relation.source_event_id == completed_event.id
    assert relation.rerun_stage_run_id != relation.source_stage_run_id
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/services/test_reruns.py tests/api/test_reruns.py -q`

- [ ] **Step 3: Extract registered operations without changing behavior**

Move each route closure into a method that receives this immutable envelope:

```python
@dataclass(frozen=True)
class WorkflowExecution:
    review_id: str
    request_payload: dict
    input_versions: tuple[ArtifactVersionView, ...]
    context: JobContext
```

Routes and reruns must call the same registry. Unknown operations, historical
failed runs, events without a completed StageRun, and deleted inputs return 409.

- [ ] **Step 4: Implement rerun lineage**

The rerun creates a new job and StageRun before execution, records
`rerun.started`, and records `rerun.completed` or `rerun.failed`. New artifacts
become current drafts and follow normal downstream stale propagation; historical
versions and source run rows remain untouched.

- [ ] **Step 5: Verify and commit**

Run the focused tests, complete backend suite, and Ruff. Commit as
`feat: rerun completed provenance events`.

### Task 6: Expose timeline, graph, and deterministic audit export APIs

**Files:**
- Create: `autometa/api/routers/provenance.py`
- Create: `autometa/services/audit_export.py`
- Modify: `autometa/api/dependencies.py`
- Modify: `autometa/api/main.py`
- Create: `tests/api/test_provenance_api.py`
- Create: `tests/api/test_audit_export.py`

**Interfaces:**
- Produces:
  - `GET /api/v1/reviews/{review_id}/provenance?after_sequence=0&limit=200`
  - `GET /api/v1/reviews/{review_id}/provenance/graph`
  - `GET /api/v1/reviews/{review_id}/audit-export`
- Export media type: `application/json`; filename:
  `autometa-review-<review-id>-audit.json`.

- [ ] **Step 1: Write failing API and export tests**

Test pagination, deterministic ordering, graph node/edge integrity, 404 isolation,
content-disposition, stable export schema version `1`, and recursive absence of
secrets, absolute paths, PDF text, and CSV contents.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/api/test_provenance_api.py tests/api/test_audit_export.py -q`

- [ ] **Step 3: Implement deterministic export assembly**

Use sorted lists and JSON serialization with `sort_keys=True`. Include hashes and
relative metadata, but exclude stored filenames/paths and file bodies. Add a
top-level `schema_version`, `exported_at`, and `product_version`.

- [ ] **Step 4: Add routes and verify HTTP headers/body**

All endpoints use Review ownership checks and return no server exception text.
The export endpoint returns a streamed attachment without first writing the
audit JSON into the Review directory.

- [ ] **Step 5: Run the backend gate and commit**

Run `.venv/bin/python -m pytest tests -q && .venv/bin/ruff check .` and commit as
`feat: expose Review provenance and audit export`.

### Task 7: Build the provenance timeline, version diff, and rerun interface

**Files:**
- Create: `frontend/src/api/provenance.ts`
- Modify: `frontend/src/api/types.ts`
- Create: `frontend/src/pages/ProvenancePage.tsx`
- Create: `frontend/src/pages/ProvenancePage.test.tsx`
- Create: `frontend/src/components/ProvenanceTimeline.tsx`
- Create: `frontend/src/components/ArtifactVersionDiff.tsx`
- Create: `frontend/src/components/RerunDialog.tsx`
- Modify: `frontend/src/components/ProvenanceRail.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Adds route: `/reviews/:reviewId/provenance`.
- Makes the existing Evidence Provenance rail a link to the full Review timeline.
- Produces typed queries for events, graph, versions, diffs, audit export, and
  rerun mutation.

- [ ] **Step 1: Write failing React tests**

Cover chronological rendering, producer/stage/type filters, event details,
version selection, add/remove/replace diff rendering, approval/revocation/stale
labels, disabled rerun for ineligible events, explicit rerun confirmation,
new-job navigation/progress, audit download, empty/error states, and 1024 px
overflow behavior.

- [ ] **Step 2: Verify RED**

Run: `cd frontend && npm test -- --run src/pages/ProvenancePage.test.tsx`

- [ ] **Step 3: Implement typed client and full timeline**

Display event sequence, timestamp, stage, producer, event label, exact input and
output version references, duration, and safe metadata. Do not render raw JSON
until the user expands an event. Use text/glyph labels in addition to color.

- [ ] **Step 4: Implement version diff, export, and rerun confirmation**

The diff viewer requests two explicit version numbers. The rerun dialog names
the operation and source timestamp and requires `Rerun` confirmation before
calling the API. The audit export button downloads only the server-generated
JSON attachment.

- [ ] **Step 5: Run frontend gates and commit**

Run:

```bash
cd frontend
npm test -- --run
npm run typecheck
npm run build
git diff --exit-code -- ../autometa/static
```

Commit source and compiled assets as `feat: add provenance timeline and reruns`.

### Task 8: Phase 2A integration, migration, privacy, and runtime gate

**Files:**
- Modify: `README.md`
- Modify: `.github/workflows/foundation.yml`
- Modify: `docs/superpowers/plans/2026-09-05-autometa-phase2a-provenance.md` only to check completed boxes and record exact verification commands.

**Interfaces:**
- Produces a locally mergeable Phase 2A branch while leaving retrieval feedback,
  source-linked PDF navigation, and expanded statistics for separate plans.

- [ ] **Step 1: Add one end-to-end backend provenance test**

Run a fake Guided workflow through all stages, record a researcher correction,
revoke approval, verify downstream stale events, rerun one completed event, and
assert a connected immutable graph plus a secret-free audit export.

- [ ] **Step 2: Verify an upgrade from a Phase 1 database**

Create a database at Alembic revision `0001`, insert a Review/artifact/job, run
`alembic upgrade head`, and prove the original rows survive with valid Phase 2
tables/defaults.

- [ ] **Step 3: Run complete automated gates**

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check .
cd frontend
npm ci
npm test -- --run
npm run typecheck
npm run build
git diff --exit-code -- ../autometa/static
```

- [ ] **Step 4: Run a real local browser gate**

Start Uvicorn with a temporary data directory. At 1024, 1280, 1440, and 1920 px,
create a Review, create/edit/approve artifacts, open the timeline, inspect a
version diff, download the audit JSON, and trigger a registered fake-free rerun
only when the configured operation can complete with the available local inputs.
Verify no console errors, remote assets, dead enabled controls, or secret fields.

- [ ] **Step 5: Record evidence, commit, and integrate locally**

Confirm `git remote -v` is empty. Record exact commands/results in this plan,
commit locally, use `verification-before-completion`, then use
`finishing-a-development-branch` to merge into `main`. Never push.

## Completion Criteria

- Every artifact version, approval, revocation, stale transition, stage run,
  failure, researcher edit, and rerun appears in an ordered Review timeline.
- Every workflow output version has graph edges from the exact immutable input
  versions used to create it.
- Historical payloads remain queryable and deterministic diffs identify changed
  paths without mutating either version.
- Only eligible completed events can rerun; reruns use persisted inputs and create
  new jobs, stage runs, output versions, events, edges, and lineage records.
- The Review audit export is deterministic, portable, and contains no credentials,
  file contents, absolute paths, manuscript data, or benchmark data.
- The React provenance workspace has real APIs for timeline, diff, rerun, revoke,
  and export, with no enabled dead controls.
- Existing Phase 1 workflow behavior and security invariants remain green.
