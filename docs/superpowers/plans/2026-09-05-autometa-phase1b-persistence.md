# AutoMeta Phase 1B Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the persistent local foundation required by AutoMeta's Phase 1 Library: SQLite Reviews, durable files, versioned artifacts, real approvals, downstream invalidation, and background jobs that survive browser disconnection.

**Architecture:** Add SQLAlchemy repositories behind focused services and versioned FastAPI resources. Store metadata in SQLite and large artifacts on disk beneath the configured data directory. Run long operations in a process-local executor while persisting job state and ordered events so reconnecting browsers can resume observation.

**Tech Stack:** Python 3.11/3.12, FastAPI, SQLAlchemy 2, Alembic, SQLite, Pydantic 2, `ThreadPoolExecutor`, SSE, pytest.

## Global Constraints

- Runtime code and user-visible copy use only AutoMeta / `autometa` naming.
- Local, single-user deployment; no authentication, accounts, roles, or remote collaboration.
- SQLite is the default Library store.
- PDFs are manually uploaded and persist under `data/reviews/<review-id>/uploads/` until Review deletion.
- API keys remain in `.env` and server memory and never enter SQLite or API responses.
- Default network bind is `127.0.0.1`; this plan does not broaden exposure.
- Browser disconnection must not cancel a running job while Uvicorn remains alive.
- On service restart, unfinished jobs become `interrupted` and can be retried later.
- No Redis, Celery, sample dataset, manuscript data, or benchmark data.
- Editing an approved artifact revokes approval and marks all downstream artifacts stale.
- Deleting a Review requires exact-name confirmation and permanently removes its database and filesystem data.
- All behavior changes follow red-green-refactor TDD.

---

### Task 1: Add SQLite and migration infrastructure

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `autometa/config.py`
- Create: `autometa/persistence/__init__.py`
- Create: `autometa/persistence/database.py`
- Create: `autometa/persistence/models.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/0001_initial.py`
- Create: `tests/persistence/test_database.py`

**Interfaces:**
- Produces: `Database(settings: Settings)`, `Database.session()`, `Database.create_schema()`, `Database.mark_running_jobs_interrupted()`, and SQLAlchemy model classes.
- Consumes: `Settings.autometa_data_dir`.

- [ ] **Step 1: Write failing database tests**

```python
from autometa.config import Settings
from autometa.persistence.database import Database
from autometa.persistence.models import Base, Job, JobState, Review, ReviewMode


def test_database_creates_all_tables(tmp_path) -> None:
    settings = Settings(_env_file=None, autometa_data_dir=tmp_path)
    database = Database(settings)
    database.create_schema()
    assert set(Base.metadata.tables) <= set(database.inspect_table_names())


def test_startup_marks_running_jobs_interrupted(tmp_path) -> None:
    database = Database(Settings(_env_file=None, autometa_data_dir=tmp_path))
    database.create_schema()
    with database.session() as session:
        review = Review(name="Review", entry_mode=ReviewMode.GUIDED)
        session.add(review)
        session.flush()
        job = Job(review_id=review.id, stage="search", state=JobState.RUNNING)
        session.add(job)
        session.commit()
        job_id = job.id
    assert database.mark_running_jobs_interrupted() == 1
    with database.session() as session:
        assert session.get(Job, job_id).state is JobState.INTERRUPTED
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/persistence/test_database.py -v
```

Expected: collection FAIL because `autometa.persistence` does not exist.

- [ ] **Step 3: Implement the persistence foundation**

Add `sqlalchemy>=2.0,<3` and `alembic>=1.13,<2` to project dependencies. Add:

```dotenv
AUTOMETA_MAX_UPLOAD_MB=100
AUTOMETA_JOB_WORKERS=2
```

to `.env.example`, and corresponding positive integer fields to `Settings`.

Define string enums:

```python
class ReviewMode(StrEnum):
    GUIDED = "guided"
    SEARCH = "search"
    SCREENING = "screening"
    EXTRACTION = "extraction"
    META_ANALYSIS = "meta_analysis"


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"
    DELETING = "deleting"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class ArtifactState(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    STALE = "stale"
```

Use UUID strings for public identifiers, UTC-aware timestamps, foreign keys,
and delete cascades. Define the models named in the approved design:
`Review`, `FileRecord`, `Job`, `JobEvent`, `StageRun`, `Artifact`,
`ArtifactVersion`, `Approval`, and `LocalSetting`.

`Database` must create `<data_dir>/autometa.db`, enable SQLite foreign keys on
every connection, yield transactional sessions, expose table names for tests,
and mark `queued`/`running` jobs as `interrupted` at startup.

- [ ] **Step 4: Run migration and database tests**

```bash
python -m pytest tests/persistence/test_database.py -v
python -m alembic upgrade head
```

Expected: tests PASS and the migration creates all tables in the configured
database without warnings.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example autometa/config.py autometa/persistence alembic.ini migrations tests/persistence/test_database.py
git diff --cached --check
git commit -m "feat: add AutoMeta SQLite persistence"
```

### Task 2: Implement Review repository, service, and API

**Files:**
- Create: `autometa/schemas/reviews.py`
- Create: `autometa/repositories/__init__.py`
- Create: `autometa/repositories/reviews.py`
- Create: `autometa/services/__init__.py`
- Create: `autometa/services/reviews.py`
- Create: `autometa/api/dependencies.py`
- Create: `autometa/api/routers/reviews.py`
- Modify: `autometa/api/main.py`
- Create: `tests/api/test_reviews.py`

**Interfaces:**
- Produces: `ReviewRepository`, `ReviewService`, `POST/GET/PATCH /api/v1/reviews`, and `GET /api/v1/reviews/{review_id}`.
- Consumes: `Database`, `Review`, `ReviewMode`, and `ReviewStatus`.

- [ ] **Step 1: Write failing Review API tests**

Use a temporary data directory and dependency override. Cover:

```python
def test_create_list_open_and_rename_review(client):
    created = client.post(
        "/api/v1/reviews",
        json={"name": "Cardiac rehabilitation", "entry_mode": "guided"},
    )
    assert created.status_code == 201
    review_id = created.json()["id"]
    assert client.get("/api/v1/reviews").json()["items"][0]["id"] == review_id
    assert client.get(f"/api/v1/reviews/{review_id}").status_code == 200
    renamed = client.patch(
        f"/api/v1/reviews/{review_id}", json={"name": "Updated review"}
    )
    assert renamed.json()["name"] == "Updated review"


def test_review_name_cannot_be_blank(client):
    response = client.post(
        "/api/v1/reviews", json={"name": "   ", "entry_mode": "guided"}
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and verify RED**

Expected: 404 or import failure because Review routes do not exist.

- [ ] **Step 3: Implement the Review API**

Define request/response schemas with trimmed names between 1 and 160
characters. `ReviewRepository` owns SQLAlchemy queries; `ReviewService` owns
validation and domain transitions. List results are ordered by `updated_at`
descending and use:

```python
class ReviewList(BaseModel):
    items: list[ReviewSummary]
    total: int
```

Register `reviews.router` under the existing `/api/v1` prefix. Do not expose
database rows directly from route handlers.

- [ ] **Step 4: Verify Review CRUD**

```bash
python -m pytest tests/api/test_reviews.py -v
python -m pytest tests/persistence tests/api -v
```

Expected: all tests PASS with isolated temporary SQLite databases.

- [ ] **Step 5: Commit**

```bash
git add autometa/schemas/reviews.py autometa/repositories autometa/services autometa/api tests/api/test_reviews.py
git diff --cached --check
git commit -m "feat: add persistent Review library API"
```

### Task 3: Add persistent PDF storage and permanent Review deletion

**Files:**
- Create: `autometa/services/files.py`
- Modify: `autometa/services/reviews.py`
- Modify: `autometa/api/routers/reviews.py`
- Create: `autometa/api/routers/files.py`
- Modify: `autometa/api/main.py`
- Create: `tests/services/test_file_storage.py`
- Create: `tests/api/test_review_deletion.py`

**Interfaces:**
- Produces: `FileStorage.save_pdf(review_id, upload) -> FileRecord`, `FileStorage.open_path(file_id) -> Path`, `DELETE /api/v1/reviews/{review_id}`, and Review-scoped upload/list/content endpoints.
- Consumes: `AUTOMETA_MAX_UPLOAD_MB`, Review ownership, and the configured data directory.

- [ ] **Step 1: Write failing storage tests**

Cover these behaviors:

```python
def test_pdf_is_stored_under_review_directory(file_storage, review):
    record = file_storage.save_bytes(
        review.id, "study.pdf", "application/pdf", b"%PDF-1.7\nbody"
    )
    assert record.relative_path.startswith(f"reviews/{review.id}/uploads/")
    assert file_storage.resolve(record).read_bytes().startswith(b"%PDF-")


def test_duplicate_pdf_reuses_record(file_storage, review):
    first = file_storage.save_bytes(review.id, "one.pdf", "application/pdf", b"%PDF-x")
    second = file_storage.save_bytes(review.id, "two.pdf", "application/pdf", b"%PDF-x")
    assert second.id == first.id


def test_non_pdf_magic_is_rejected(file_storage, review):
    with pytest.raises(InvalidUpload):
        file_storage.save_bytes(review.id, "fake.pdf", "application/pdf", b"not-pdf")
```

Add API tests proving the wrong confirmation name returns 409 and the exact
name deletes both the database row and `data/reviews/<review-id>` directory.

- [ ] **Step 2: Run tests and verify RED**

Expected: imports or endpoints fail because file storage and deletion do not exist.

- [ ] **Step 3: Implement safe local file lifecycle**

Normalize display filenames but store files using generated UUID names. Reject
path separators, invalid PDF magic bytes, non-PDF MIME values, empty uploads,
and payloads larger than the configured limit. Calculate SHA-256 while writing
to a temporary file and atomically move valid files into the Review directory.

Provide:

```text
POST /api/v1/reviews/{review_id}/files
GET  /api/v1/reviews/{review_id}/files
GET  /api/v1/files/{file_id}/content
```

The content endpoint returns `application/pdf`, supports Starlette range
responses when available, and verifies Review/file ownership through the
repository rather than trusting a path from the client.

Deletion requires JSON `{ "confirmation_name": "<exact review name>" }`.
Mark the Review `deleting`, reject new jobs, rename its directory to a unique
deletion-staging path on the same volume, delete the database row, and remove
the staged directory. Restore the directory if the database transaction fails.

- [ ] **Step 4: Verify storage, traversal resistance, and deletion**

```bash
python -m pytest tests/services/test_file_storage.py tests/api/test_review_deletion.py -v
python -m pytest tests/persistence tests/services tests/api -v
```

Expected: all tests PASS; no test writes outside its temporary data directory.

- [ ] **Step 5: Commit**

```bash
git add autometa/services autometa/api tests/services tests/api
git diff --cached --check
git commit -m "feat: persist Review PDF files safely"
```

### Task 4: Add versioned artifacts, approvals, and stale propagation

**Files:**
- Create: `autometa/schemas/artifacts.py`
- Create: `autometa/repositories/artifacts.py`
- Create: `autometa/services/artifacts.py`
- Create: `autometa/api/routers/artifacts.py`
- Modify: `autometa/api/main.py`
- Create: `tests/services/test_artifacts.py`
- Create: `tests/api/test_artifacts.py`

**Interfaces:**
- Produces: `ArtifactService.save_draft`, `ArtifactService.approve`, `ArtifactService.revoke`, and Review-scoped artifact APIs.
- Consumes: artifact order `question_pico`, `query`, `records`, `selected_studies`, `sources`, `plan`, `code`, `result`.

- [ ] **Step 1: Write failing artifact transition tests**

```python
def test_only_approved_artifact_can_be_consumed(artifact_service, review):
    draft = artifact_service.save_draft(review.id, "query", {"query": "sleep"})
    assert artifact_service.get_approved(review.id, "query") is None
    artifact_service.approve(review.id, draft.artifact_id, draft.version)
    assert artifact_service.get_approved(review.id, "query").payload == {"query": "sleep"}


def test_editing_approved_artifact_stales_downstream(artifact_service, review):
    query = artifact_service.save_draft(review.id, "query", {"query": "sleep"})
    artifact_service.approve(review.id, query.artifact_id, query.version)
    records = artifact_service.save_draft(review.id, "records", {"count": 10})
    artifact_service.approve(review.id, records.artifact_id, records.version)
    artifact_service.save_draft(review.id, "query", {"query": "sleep AND trial"})
    assert artifact_service.get_state(review.id, "query") == "draft"
    assert artifact_service.get_state(review.id, "records") == "stale"
```

- [ ] **Step 2: Run tests and verify RED**

Expected: imports fail because the artifact service does not exist.

- [ ] **Step 3: Implement immutable versions and approvals**

Use this dependency order:

```python
ARTIFACT_ORDER = (
    "question_pico",
    "query",
    "records",
    "selected_studies",
    "sources",
    "plan",
    "code",
    "result",
)
```

`save_draft` creates an immutable `ArtifactVersion` containing a canonical JSON
payload and SHA-256 hash, makes it current, revokes current approval if needed,
and marks all later artifacts stale in one transaction. `approve` accepts only
the current draft version. `revoke` leaves the version intact and sets the
artifact back to draft.

Expose list/get/save/approve/revoke endpoints under:

```text
/api/v1/reviews/{review_id}/artifacts
/api/v1/reviews/{review_id}/artifacts/{kind}
/api/v1/reviews/{review_id}/artifacts/{kind}/approve
/api/v1/reviews/{review_id}/artifacts/{kind}/revoke
```

- [ ] **Step 4: Verify domain and API transitions**

```bash
python -m pytest tests/services/test_artifacts.py tests/api/test_artifacts.py -v
python -m pytest tests/persistence tests/services tests/api -v
```

Expected: all tests PASS, including stale propagation and invalid-version conflicts.

- [ ] **Step 5: Commit**

```bash
git add autometa/schemas/artifacts.py autometa/repositories/artifacts.py autometa/services/artifacts.py autometa/api tests
git diff --cached --check
git commit -m "feat: add artifact approval lifecycle"
```

### Task 5: Add persistent process-local jobs and SSE replay

**Files:**
- Create: `autometa/schemas/jobs.py`
- Create: `autometa/repositories/jobs.py`
- Create: `autometa/jobs/__init__.py`
- Create: `autometa/jobs/manager.py`
- Create: `autometa/api/routers/jobs.py`
- Modify: `autometa/api/main.py`
- Create: `tests/jobs/test_job_manager.py`
- Create: `tests/api/test_jobs.py`

**Interfaces:**
- Produces: `JobManager.submit(review_id, stage, operation) -> JobView`, `JobContext.emit`, `JobManager.cancel_review`, job status API, and replayable SSE events.
- Consumes: `Database`, `Job`, `JobEvent`, and configured worker count.

- [ ] **Step 1: Write failing job tests**

```python
def test_job_continues_without_sse_subscriber(job_manager, review, wait_until):
    def operation(context):
        context.emit("progress", {"completed": 1, "total": 1})
        return {"ok": True}

    job = job_manager.submit(review.id, "search", operation)
    wait_until(lambda: job_manager.get(job.id).state == "succeeded")
    events = job_manager.events(job.id, after_sequence=0)
    assert [event.event_type for event in events] == ["queued", "running", "progress", "succeeded"]


def test_conflicting_stage_job_is_rejected(job_manager, review, blocking_operation):
    job_manager.submit(review.id, "screening", blocking_operation)
    with pytest.raises(JobConflict):
        job_manager.submit(review.id, "screening", blocking_operation)
```

Add API coverage proving `after=2` replays only events with sequence greater
than 2 and that an unknown job returns 404.

- [ ] **Step 2: Run tests and verify RED**

Expected: imports fail because `JobManager` does not exist.

- [ ] **Step 3: Implement the job manager**

Use a bounded `ThreadPoolExecutor`. Persist `queued` before submission, change
to `running` inside the worker, and commit every event with a monotonically
increasing sequence scoped to the job. Store a JSON-safe result reference or
error summary; never store secrets or unnecessary PDF text in events.

SSE endpoint:

```text
GET /api/v1/jobs/{job_id}/events?after=<sequence>
```

It first sends stored events after the requested sequence, then polls for new
events until the job reaches a terminal state or the client disconnects.
Disconnecting the generator must not cancel the future.

`cancel_review(review_id)` cancels queued futures and signals cooperative
cancellation to running operations. A running operation checks
`JobContext.cancelled` between bounded units of work.

- [ ] **Step 4: Verify persistence and reconnection behavior**

```bash
python -m pytest tests/jobs/test_job_manager.py tests/api/test_jobs.py -v
python -m pytest tests/persistence tests/services tests/jobs tests/api -v
```

Expected: all tests PASS without sleeps longer than 100 ms; executors shut down cleanly.

- [ ] **Step 5: Commit**

```bash
git add autometa/schemas/jobs.py autometa/repositories/jobs.py autometa/jobs autometa/api tests/jobs tests/api
git diff --cached --check
git commit -m "feat: add persistent background jobs"
```

### Task 6: Wire application lifespan and safe deletion coordination

**Files:**
- Modify: `autometa/api/main.py`
- Modify: `autometa/api/dependencies.py`
- Modify: `autometa/services/reviews.py`
- Modify: `autometa/jobs/manager.py`
- Create: `tests/api/test_lifespan.py`
- Modify: `tests/api/test_review_deletion.py`

**Interfaces:**
- Produces: initialized application services in `app.state`, startup interruption recovery, executor shutdown, and deletion/job coordination.
- Consumes: Database, ReviewService, FileStorage, ArtifactService, and JobManager.

- [ ] **Step 1: Write failing lifespan tests**

Cover:

```python
def test_lifespan_initializes_database_and_services(client):
    assert client.app.state.database.inspect_table_names()
    assert client.app.state.review_service is not None
    assert client.app.state.job_manager is not None


def test_delete_review_cancels_jobs_before_removing_files(client, seeded_review):
    response = client.request(
        "DELETE",
        f"/api/v1/reviews/{seeded_review.id}",
        json={"confirmation_name": seeded_review.name},
    )
    assert response.status_code == 204
    assert not seeded_review.directory.exists()
```

- [ ] **Step 2: Run tests and verify RED**

Expected: app state services are missing or deletion does not coordinate jobs.

- [ ] **Step 3: Implement FastAPI lifespan**

Use one async lifespan context to:

1. Create the configured data directory.
2. Initialize the database.
3. Mark queued/running jobs interrupted.
4. Create repositories and services.
5. Create the bounded JobManager.
6. Attach dependencies to `app.state`.
7. Shut the executor down on application shutdown.

Review deletion must reject new work, cancel or cooperatively stop jobs, and
perform the staged directory/database deletion defined in Task 3.

- [ ] **Step 4: Run lifecycle and full tests**

```bash
python -m pytest tests/api/test_lifespan.py tests/api/test_review_deletion.py -v
python -m pytest tests -v
```

Expected: all tests PASS and no worker thread remains after TestClient exits.

- [ ] **Step 5: Commit**

```bash
git add autometa/api autometa/services autometa/jobs tests
git diff --cached --check
git commit -m "feat: initialize persistent application services"
```

### Task 7: Add safe system status

**Files:**
- Create: `autometa/schemas/system.py`
- Create: `autometa/api/routers/system.py`
- Modify: `autometa/api/main.py`
- Create: `tests/api/test_system_status.py`

**Interfaces:**
- Produces: `GET /api/v1/system/status` without secret-bearing fields.
- Consumes: `Settings.safe_summary()` and database connectivity.

- [ ] **Step 1: Write failing status tests**

```python
def test_system_status_reports_readiness_without_secrets(client):
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["product"] == "AutoMeta"
    assert payload["database"] == "ready"
    assert "api_key" not in payload
    assert "secret" not in response.text.lower()
```

Configure the test client with an endpoint containing synthetic URL credentials
and a query value, then assert neither appears in the response.

- [ ] **Step 2: Run test and verify RED**

Expected: 404 because the system status endpoint does not exist.

- [ ] **Step 3: Implement safe status response**

Return only product/version, database readiness, provider base URL, selected
model names, whether a key is configured, data directory, bind host, and port.
Name the boolean `provider_configured` rather than `api_key_configured` so no
credential-shaped field enters the public API. Sanitize the provider URL by
removing user information and its query/fragment before returning it. Never
include environment values beyond the explicit safe allowlist.

- [ ] **Step 4: Run status and secret scans**

```bash
python -m pytest tests/api/test_system_status.py -v
python -m pytest tests -v
git grep -n 'llm_api_key\|pubmed_api_key' -- autometa/api autometa/schemas
```

Expected: tests PASS; any grep match is internal dependency access and no
response schema contains a secret value or secret-named response field.

- [ ] **Step 5: Commit**

```bash
git add autometa/schemas/system.py autometa/api tests/api/test_system_status.py
git diff --cached --check
git commit -m "feat: expose safe AutoMeta system status"
```

### Task 8: Phase 1B verification gate

**Files:**
- Modify only when verification reveals a defect: files listed in Tasks 1–7

**Interfaces:**
- Produces: a verified persistence foundation ready for the React/Library UI plan.

- [ ] **Step 1: Run the complete test and static gate**

```bash
python -m pytest tests -v
python -m compileall -q autometa tests
git diff --check
git status --short --untracked-files=no
```

Expected: all tests PASS, compilation succeeds, and tracked state is clean.

- [ ] **Step 2: Exercise a temporary real server**

Start AutoMeta with a temporary data directory and no real provider call:

```bash
AUTOMETA_DATA_DIR=/tmp/autometa-phase1b-check python -m autometa serve
```

Verify in another terminal:

```bash
curl -fsS http://127.0.0.1:8016/api/v1/health
curl -fsS http://127.0.0.1:8016/api/v1/system/status
curl -fsS -X POST http://127.0.0.1:8016/api/v1/reviews \
  -H 'Content-Type: application/json' \
  -d '{"name":"Release check","entry_mode":"guided"}'
```

Expected: health and system endpoints return safe JSON; Review creation returns
201; no key appears in output.

- [ ] **Step 3: Verify the public boundary and database locality**

```bash
git ls-files | rg '(^|/)(\.env|data|runs|paper_figures|baselines|docling_models)(/|$)' && exit 1 || true
test ! -e autometa/autometa.db
```

Expected: no private runtime path is tracked and no database was written inside
the package.

- [ ] **Step 4: Commit verification fixes only if needed**

If verification required a change, first add a failing regression test, fix it,
rerun the complete gate, and commit:

```bash
git add autometa tests pyproject.toml .env.example README.md migrations alembic.ini
git diff --cached --check
git commit -m "fix: complete AutoMeta persistence verification"
```

If the gate required no change, do not create an empty commit.

## Phase 1B Completion Criteria

- Reviews persist in SQLite and can be created, listed, opened, renamed, and deleted.
- Uploaded PDFs persist in Review-scoped directories and are ownership-checked.
- Exact-name deletion removes all Review data.
- Artifact drafts, immutable versions, approvals, revocations, and stale propagation work.
- Background jobs continue without an SSE subscriber and persist ordered progress.
- Startup converts abandoned queued/running jobs to interrupted.
- The system status endpoint exposes readiness without credential material.
- All storage and tests use configurable or temporary data directories.
- The clean public repository remains free of manuscripts, experiments, benchmarks, credentials, and user data.
