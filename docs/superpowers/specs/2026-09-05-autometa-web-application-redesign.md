# AutoMeta Web Application Redesign

**Status:** Approved design

**Date:** 2026-09-05

**Product name:** AutoMeta

**Deployment model:** Local, single-user, self-hosted

## 1. Objective

Transform the existing AutoMeta web application into a polished, open-source,
locally deployed evidence-synthesis workspace. The redesigned product will use
the visual language and workflow clarity of the manuscript figures while all
displayed data and actions remain connected to real application behavior.

The implementation will preserve the existing core capabilities:

1. Derive and edit a PICO protocol from a research question.
2. Construct, review, and execute a PubMed search.
3. Rank retrieved records using evidence-backed PICO-dimension judgements.
4. Extract user-defined fields from manually uploaded full-text PDFs.
5. Review and edit extracted values and supporting quotations.
6. Generate, approve, and execute deterministic meta-analysis plans.
7. Export intermediate and final artifacts.

The production application will not reproduce or embed the manuscript case
study, benchmark identifiers, benchmark records, numerical results, or frozen
paper-figure data.

## 2. Confirmed Product Decisions

- Use `AutoMeta` everywhere. The legacy product and package names will be
  removed from runtime code, package names, commands, logs, comments, and
  documentation.
- Use React, TypeScript, and Vite for the frontend.
- Use FastAPI and Uvicorn for the backend.
- Commit both frontend source code and the compiled frontend assets needed by
  FastAPI, allowing ordinary users to run AutoMeta without installing Node.js.
- Support local, single-user deployment only. Authentication, accounts, roles,
  and remote multi-user collaboration are outside the first public release.
- Use SQLite as the default Library and workflow-state database.
- Persist uploaded PDFs beneath `data/reviews/<review-id>/uploads/` until the
  user permanently deletes the corresponding Review.
- Support manual PDF upload only. AutoMeta will not download publisher, DOI, or
  PMC full text in the initial release.
- Use an OpenAI-compatible provider abstraction with one default model and
  optional stage-specific model overrides.
- Keep API keys in `.env` and server memory only. Never store or return them.
- Use English throughout the product interface, API documentation, code
  comments, and primary README.
- Do not include a Chinese README in the first public release.
- Use the manuscript's Logo A: the coordinating center node with four agent
  satellites. Preserve its navy rounded-square field, white center and side
  nodes, and teal upper node when creating the production SVG asset.
- Use the MIT License with `Copyright (c) 2026 AutoMeta Contributors`.
- Officially validate macOS and Windows CPU installations. Linux is supported
  through Docker. GPU/CUDA setup is optional and outside baseline support.
- Support desktop and large-tablet layouts with a minimum effective width of
  1024 px. Phone layouts are outside the supported interface.
- Use a pure-Python statistical engine and cross-check deterministic fixtures
  against R `metafor` during development. End users will not need R.
- Ship no user-facing example or benchmark dataset. Unit tests may contain
  minimal deterministic values constructed inside test code.

## 3. Scope Boundaries

### 3.1 In scope

- Guided end-to-end reviews.
- Independent entry into Search, Screening, Extraction, or Meta-analysis.
- A functional local Library in Phase 1.
- Real approval gates that control downstream execution.
- Background jobs that survive a browser disconnection while Uvicorn remains
  running.
- Persistent PDFs, parsed artifacts, exports, and generated figures.
- Full evidence provenance, reruns, PDF source navigation, and expanded
  statistical outputs in Phase 2.

### 3.2 Out of scope

- Reproduction of the manuscript demonstration or benchmark results.
- Public benchmark browsing in the production UI.
- Automatic acquisition of copyrighted or open-access PDFs.
- Mobile-phone optimization.
- User authentication, permissions, teams, or hosted multi-tenancy.
- Redis, Celery, or another external job service in the first public release.
- Mandatory GPU support.

## 4. Repository and Runtime Architecture

The open-source repository will be a monorepo:

```text
AutoMeta/
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
├── autometa/
│   ├── api/
│   ├── agents/
│   ├── services/
│   ├── schemas/
│   ├── repositories/
│   ├── integrations/
│   ├── jobs/
│   ├── stats/
│   └── static/              # committed Vite build
├── migrations/
├── tests/
├── docs/
├── scripts/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

The browser communicates only with the local FastAPI service. FastAPI serves
the compiled SPA and versioned JSON/SSE endpoints. Domain services isolate the
web layer from agent implementations, file storage, LLM calls, and statistical
functions.

The primary cross-platform command will be:

```bash
python -m autometa serve
```

This command will read `AUTOMETA_HOST` and `AUTOMETA_PORT` and start Uvicorn.
The documented defaults will be `127.0.0.1` and `8016`. Direct Uvicorn usage
will also be documented for advanced users.

## 5. Open-Source Repository Hygiene

The AutoMeta workspace will become an independent Git repository instead of
using the accidental parent repository under the user's home directory.

Before any broad Git add operation, `.gitignore` will exclude:

- `.env` and all credential-bearing files.
- `data/`, uploaded PDFs, SQLite files, parsed documents, exports, and figures.
- `runs/`, logs, caches, temporary files, and Python bytecode.
- `paper_figures/`, manuscript DOCX files, manuscript backups, references, and
  evaluation artifacts.
- local model weights and baseline repositories.
- `node_modules/` and frontend development caches.

The public repository will include only application source, compiled frontend
assets, migrations, tests, operational documentation, and licensing files.

## 6. Product Navigation and Review Modes

The top bar will contain:

- AutoMeta Logo A and wordmark.
- `Evidence Synthesis Workspace` descriptor.
- Current Review name when a Review is open.
- `New Review`.
- `Library`.
- `System Status`.
- Application version.

There will be no production `Benchmarks` navigation item and no nonfunctional
controls.

Creating a Review requires selecting one of five entry modes:

1. `Guided Review`: start with a research question and run all four agents.
2. `Search`: start with PICO and PubMed retrieval settings.
3. `Screening`: import PubMed, CSV, or JSON records and provide PICO context.
4. `Extraction`: provide minimal study context, define fields, and upload PDFs.
5. `Meta-analysis`: upload CSV datasets and configure a statistical plan.

Every entry mode creates a normal persisted Review. An independently started
stage can subsequently proceed downstream when its required output is approved.

## 7. Global Workflow Shell

The manuscript's four-agent rail becomes the persistent product navigation:

1. Search Agent — produces reviewed Query and Records artifacts.
2. Screening Agent — produces a Selected Studies artifact.
3. Extraction Agent — produces Source-linked Values artifacts.
4. Meta-analysis Agent — produces Plan, Code, and Result artifacts.

Review Setup precedes the rail and is not presented as a fifth agent.

The stage rail displays real state, not decorative progress. Supported states:

```text
not_started
running
draft
awaiting_approval
approved
failed
interrupted
stale
```

The bottom provenance rail initially summarizes the artifacts completed in the
current Review. In Phase 2 it becomes an entry point to the full event record.

## 8. Frontend Design System

The product will adapt the manuscript's editorial-precision visual system:

- White surfaces on a restrained grey canvas.
- Deep navy structural text.
- Blue for Search, teal for Screening, purple for Extraction, and ochre for
  Meta-analysis.
- Semantic match, uncertain, mismatch, and not-found states always combine
  color with text or a glyph.
- Tabular numerals in scientific tables.
- Compact radii, light borders, and restrained shadows.
- Dense but readable research-workspace layouts rather than marketing pages.

The fixed 1440 px paper layouts will be converted into responsive desktop and
large-tablet components. Wide scientific tables may scroll horizontally within
their panels. The global shell must remain usable at 1024 px.

The Logo A inline SVG will be converted into both:

- `frontend/public/autometa-mark.svg`.
- A reusable, accessible React `AutoMetaLogo` component.

No external font, Tailwind CDN, or runtime design dependency will be required.

## 9. Phase 1 Functional Design

### 9.1 Review Setup

- Enter a research question or required stage-specific context.
- Derive PICO through the configured model.
- Edit Population, Intervention, Comparator, and Outcomes.
- Configure PubMed limits and internal concurrency.
- Autosave changes to SQLite.
- Do not provide a manuscript or benchmark example.

### 9.2 Search Agent

The Search Agent has two views.

`Query`:

- Generate a field-tagged PubMed query.
- Present concept blocks and the complete raw query.
- Permit direct editing.
- Validate required syntax before approval.
- Store generated and edited forms separately at the data-model level.
- Require `Approve Query` before final execution.

`Records`:

- Execute the approved query against PubMed.
- Display PMID, title, author, year, journal, publication type, and abstract.
- Support search, sorting, pagination, CSV, JSON, and RIS exports.
- Pass the approved Records artifact to Screening.

Retrieval-informed seed expansion is a Phase 2 capability. Phase 1 will not
claim that it occurred.

### 9.3 Screening Agent

- Run the existing PICO-dimension ranking pipeline as a persistent background
  job.
- Display P, I, C, and O scores independently.
- Display the real abstract quotation or evidence text for every judgement.
- Sort by score and confidence without implying automatic exclusion.
- Support filters, search, pagination, bulk selection, and Top N selection.
- Let the researcher approve the final Selected Studies set.
- Preserve uncertain records for human selection.

### 9.4 Extraction Agent

- Persist manually uploaded PDFs in the Review directory.
- Match uploaded filenames to selected records when a PMID is available.
- Permit extraction-only Reviews without an upstream screening artifact.
- Define study-characteristic and outcome-result fields.
- Stream parse and extraction progress from a persisted background job.
- Display editable values, confidence, filename, outcome, and verbatim citation.
- Mark user-modified fields as researcher edits.
- Select result rows for Meta-analysis.
- Export CSV and JSON.

Phase 1 will display only source details that the current parser genuinely
returns. It will not synthesize page or table locations.

### 9.5 Meta-analysis Agent

- Accept approved extraction rows or manually uploaded CSV files.
- Generate a structured method plan.
- Render the plan as editable fields plus human-readable text.
- Display assumptions, warnings, column mappings, effect source, effect measure,
  model choice, continuity correction, and output selections.
- Require explicit Plan approval before calculation.
- Stop on invalid data or unsupported methods.
- Never silently substitute an effect measure, model, or estimator.
- Display pooled effect, confidence interval, Q, I-squared, tau-squared, study
  effects, weights, warnings, logs, and generated calculation code when present.

The advanced pure-Python statistics and graphical output are completed in
Phase 2. Phase 1 will label only calculations that the current validated engine
actually performs.

### 9.6 Library

Phase 1 Library supports:

- Create Review.
- List Reviews by modification time.
- Search by Review name.
- Display mode, current stage, status, and last update.
- Open and continue a Review.
- Permanently delete a Review after name confirmation.

## 10. Persistence Model

Phase 1 establishes the versioning foundation even though the complete history
UI arrives in Phase 2.

Core tables:

- `reviews`: identity, name, entry mode, state, current stage, timestamps.
- `files`: Review ownership, original filename, stored path, SHA-256, MIME,
  size, parse state, and timestamps.
- `jobs`: job kind, state, progress, error, start/end times, and retry source.
- `job_events`: ordered progress events used for SSE reconnection.
- `stage_runs`: stage, input artifact IDs, job ID, status, and timing.
- `artifacts`: semantic type and current version.
- `artifact_versions`: immutable JSON payload or file reference plus hash.
- `approvals`: artifact version, approval state, and timestamp.
- `settings`: nonsecret local acknowledgements and UI preferences.

Phase 2 adds explicit event and graph models:

- `review_events`.
- `researcher_edits`.
- `provenance_edges`.
- `rerun_relationships`.

SQLite migrations will be managed by Alembic. Database and user artifacts are
never committed to Git.

## 11. Autosave, Approval, and Invalidation

- Editable screens autosave a draft after a short debounce.
- Each save creates a new immutable artifact version or updates an unapproved
  draft according to the repository service's transaction rules.
- Only an approved artifact version can be consumed downstream.
- Editing an approved artifact immediately removes its approved status.
- All downstream artifacts and stage runs become `stale`.
- Stale artifacts remain visible for comparison but cannot be treated as valid
  inputs.
- Approval is transactional: artifact version and approval must be committed
  together.

## 12. Background Job and Progress Model

Long-running model, screening, parsing, extraction, and statistical operations
will not be owned by an SSE connection.

1. The frontend creates a job and receives a `job_id`.
2. An in-process worker executes the job.
3. State and ordered progress events are written to SQLite.
4. SSE subscribers receive events after their last observed sequence number.
5. Closing the browser disconnects only the subscriber; the job continues.
6. Reopening the Review reconnects to stored progress and subsequent events.
7. At application startup, jobs left in `running` state become `interrupted`.
8. The UI can retry an interrupted job from its persisted input artifacts.

The first release avoids Redis and Celery. Internal concurrency remains
configurable but a single Review cannot run conflicting jobs for the same stage.

## 13. OpenAI-Compatible Provider

The server configuration will support:

```dotenv
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
PROTOCOL_MODEL=
SEARCH_MODEL=
SCREENING_MODEL=
EXTRACTION_MODEL=
META_ANALYSIS_MODEL=
PUBMED_API_KEY=
AUTOMETA_DATA_DIR=./data
AUTOMETA_HOST=127.0.0.1
AUTOMETA_PORT=8016
```

`LLM_MODEL` is the global default. A nonempty stage-specific value overrides it
for that stage. The API key remains in environment-backed server configuration,
is redacted from logs, is never persisted, and is never returned by the system
status endpoint.

The default bind address is localhost. Binding to `0.0.0.0` requires explicit
configuration and produces a security warning because the first release has no
authentication.

## 14. PDF Storage, Privacy, and Deletion

Files are stored at:

```text
data/reviews/<review-id>/
├── uploads/
├── parsed/
├── exports/
└── figures/
```

Upload validation includes extension, MIME type, PDF magic bytes, configurable
size limit, safe filename normalization, and SHA-256 calculation. Duplicate
files within a Review are detected by hash.

Before the first Extraction run, the UI explains that relevant PDF text chunks
will be sent to the configured OpenAI-compatible model provider. The local
acknowledgement is stored without storing credentials.

Deleting a Review requires typing its name. The deletion transaction prevents
new jobs, stops or cancels associated in-process work where safely possible,
removes database records, and deletes uploaded PDFs, parsed content, exports,
and generated figures. The interface states that deletion is permanent.

## 15. Phase 2 Provenance and Rerun Design

The complete provenance sequence is:

```text
Question/PICO -> Query -> Records -> Selected Studies -> Sources
-> Plan -> Code -> Result
```

Every event records:

- Review and stage.
- Event type.
- Producer: agent, researcher, or deterministic system function.
- Input and output artifact versions.
- Timestamp and elapsed time.
- Model/provider metadata where applicable, excluding secrets.
- Parser or statistical-library version where applicable.
- Correction, approval, revocation, or failure metadata.

The provenance interface supports JSON export, version diff, approval
revocation, and rerunning from a valid event. Rerunning creates new versions and
relationships; it never overwrites the historical event chain.

## 16. Phase 2 Retrieval-Informed Search

The real search sequence will be:

1. Generate a field-tagged seed query from PICO.
2. Retrieve a small seed set from PubMed.
3. Mine titles, abstracts, and indexed terms for candidate vocabulary.
4. Generate an expanded query.
5. Display term additions, removals, sources, and result-count change.
6. Allow researcher editing.
7. Approve and execute the final query.

The production interface never displays benchmark recall, reference-study
coverage, or manuscript-specific performance claims.

## 17. Phase 2 Source-Linked PDF Reader

Extraction evidence will be extended with:

- File ID.
- Page number.
- Element type.
- Table and cell identifiers where available.
- Text span.
- Bounding box where available.
- Direct or derived extraction type.
- Derivation description.
- Parser version.

The frontend will bundle PDF.js locally. Evidence navigation follows a strict
degradation policy:

1. Coordinates available: open the page and highlight the region.
2. Page only: open the page and show the quotation alongside it.
3. Quotation only: show `Exact page location unavailable`.
4. Never infer or fabricate a page, table, row, column, or coordinate.

## 18. Phase 2 Statistical Engine

`autometa.stats` will use NumPy, SciPy, Pandas, and Matplotlib. It will provide:

- Fixed-effect inverse-variance models.
- DerSimonian-Laird random effects.
- Restricted maximum likelihood random effects.
- MD, SMD, Hedges g, OR, RR, and RD.
- Q, I-squared, tau-squared, and between-study standard deviation.
- Prediction intervals.
- Leave-one-out analysis.
- Subgroup analysis.
- Study weights and study-level confidence intervals.
- Forest plots exported as SVG, PNG, and PDF.

Generated scripts call the same versioned functions used by the server. The
application will not execute arbitrary model-authored Python. Invalid inputs or
nonconvergence produce explicit errors and no silent method fallback.

Deterministic unit fixtures will be cross-checked against R `metafor` during
development. These fixtures are test values, not a user-facing example dataset
or reproduction of the manuscript case.

## 19. API Shape

The API will be versioned under `/api/v1`. Representative resources:

- `/system/status`
- `/reviews`
- `/reviews/{review_id}`
- `/reviews/{review_id}/files`
- `/reviews/{review_id}/stages/{stage}/runs`
- `/reviews/{review_id}/artifacts`
- `/reviews/{review_id}/approvals`
- `/jobs/{job_id}`
- `/jobs/{job_id}/events`
- `/files/{file_id}/content`
- `/files/{file_id}/pages/{page_number}`
- `/reviews/{review_id}/provenance` in Phase 2
- `/reviews/{review_id}/reruns` in Phase 2

File content endpoints support HTTP range requests for PDF.js. Every endpoint
validates that local resources belong to the requested Review.

## 20. Error Handling

- Validation errors appear next to the affected field and in an accessible
  summary.
- Network and provider errors preserve the current draft.
- Background job failures retain logs suitable for local diagnosis while
  redacting credentials and unnecessary PDF content.
- Interrupted jobs can be retried from persisted inputs.
- Partial extraction results remain reviewable but are clearly labeled.
- Statistical failures do not produce a result card or forest plot.
- Downstream stages identify the exact stale or missing prerequisite.

## 21. Cross-Platform and Dependency Policy

- Supported Python versions: 3.11 and 3.12.
- Frontend development uses Node.js 20 or newer.
- Ordinary runtime users use committed compiled assets and do not require Node.
- macOS and Windows CPU setup receive native installation instructions and CI
  verification.
- Linux is supported through Docker.
- File and subprocess handling use cross-platform Python APIs.
- Bash is never the only supported entry point; optional shell and PowerShell
  helpers may wrap the same Python command.
- GPU dependencies are isolated in optional extras and are absent from the
  default installation.

## 22. Testing Strategy

### Backend

- Repository and migration tests using temporary SQLite databases.
- API contract tests for every Review mode and stage.
- Provider tests using deterministic fake OpenAI-compatible responses.
- Job persistence, reconnection, interruption, and retry tests.
- File validation, ownership, deduplication, and deletion tests.
- Approval and downstream invalidation tests.
- Statistical unit and cross-validation tests.

### Frontend

- Component tests for stage rail, tables, editors, approvals, errors, and empty
  states.
- API state and SSE reconnection tests.
- Browser tests for Guided Review and every independent stage entry.
- Visual checks at 1024, 1280, 1440, and 1920 px widths.
- Accessibility checks for keyboard navigation, labels, dialogs, and semantic
  status indicators.

### Packaging

- Clean installation on macOS and Windows CPU environments.
- Docker build and startup test.
- CI rebuilds the Vite frontend and fails if committed static assets differ.
- Secret scan and assertion that runtime data and manuscript assets are not
  tracked.
- Repository-wide assertion that the legacy names do not remain in public
  runtime source or documentation.

## 23. Delivery Phases

### Phase 1: Real product foundation

1. Establish the safe independent repository and packaging boundary.
2. Add regression tests around the existing behavior.
3. Rename the legacy product and package to AutoMeta.
4. Introduce SQLite, migrations, files, jobs, and Review repositories.
5. Introduce the OpenAI-compatible provider abstraction.
6. Build the React shell, Logo A assets, Library, and Review creation modes.
7. Migrate Review Setup and Search.
8. Migrate Screening.
9. Migrate Extraction and persistent PDF handling.
10. Migrate Meta-analysis planning and existing deterministic results.
11. Add approvals, autosave, stale-state propagation, and job reconnection.
12. Complete macOS and Windows CPU verification, Docker, README, and MIT
    licensing.

### Phase 2: Full provenance and scientific workspace

1. Add immutable event history, diffs, revocation, and rerun relationships.
2. Add retrieval-informed seed expansion.
3. Preserve page, table, text, and bounding-box metadata during parsing.
4. Integrate the PDF.js reader and evidence highlighting.
5. Implement and validate the complete pure-Python statistical library.
6. Add forest plots, prediction intervals, leave-one-out, and subgroup outputs.
7. Complete provenance export and end-to-end audit tests.

## 24. Acceptance Criteria

The redesign is complete only when:

- The runtime product is named AutoMeta throughout.
- No manuscript experiment data or paper assets are required by the app.
- Every visible action has a real implementation.
- All scientific results derive from real user inputs and persisted artifacts.
- Guided and independent stage workflows both work.
- Basic Library behavior is functional in Phase 1.
- Browser disconnection does not cancel active jobs.
- PDF files persist locally until Review deletion.
- Approval and downstream invalidation rules are enforced.
- API keys never reach the browser or database.
- The app binds to localhost by default.
- A user can clone the repository, install Python dependencies, configure
  `.env`, and start the application through the Uvicorn-backed command without
  installing Node.js.
- macOS and Windows CPU verification passes.
- The interface remains usable at widths of 1024 px and above.
- Phase 2 provenance, PDF navigation, and statistical outputs never fabricate
  unavailable evidence or silently change methods.
