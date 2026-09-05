# AutoMeta

AutoMeta is a local, single-user application for researcher-supervised
evidence synthesis. Its React workspace supports a guided four-stage Review or
independent entry into Search, Screening, Extraction, and Meta-analysis.

The repository does not ship a sample, demonstration, or benchmark dataset.
Users must provide their own inputs and keep credentials in a local `.env`
file. `.env.example` defines the public configuration contract without secrets.

## Start the local server

After installing the Python dependencies, macOS and Windows use the same
command:

```bash
python -m autometa serve
```

```powershell
python -m autometa serve
```

AutoMeta listens on `127.0.0.1:8016` by default. Set `AUTOMETA_HOST=0.0.0.0`
only when local-network access is intentional; the first release does not
provide authentication.

The approved product direction and repository architecture are documented in
the [AutoMeta web application redesign specification](docs/superpowers/specs/2026-09-05-autometa-web-application-redesign.md).

## Requirements

- Python 3.11 or 3.12
- macOS or Windows for the native CPU installation

GPU acceleration is optional and is not part of the default installation. The
base package does not use a CUDA-specific package index or require a
GPU-specific PyTorch build.

The foundation test suite runs on macOS and Windows with both supported Python
versions. Linux packaging will be verified through Docker during release
hardening.

## Install

Create and activate a virtual environment, then install AutoMeta:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m alembic upgrade head
```

On Windows PowerShell, activate the environment with:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m alembic upgrade head
```

Copy `.env.example` to `.env` and configure the OpenAI-compatible endpoint,
API key, and model before starting the server.

Open <http://127.0.0.1:8016> and create a Review. The Library, uploaded files,
drafts, approvals, generated code, and results persist under the configured
local data directory.

## Docker on Linux

The image uses Python 3.12, the committed frontend assets, and CPU-only runtime
dependencies; Node.js is not installed in the image. From the repository root:

```bash
docker build -t autometa:local .
docker run --rm --name autometa \
  --publish 127.0.0.1:8016:8016 \
  --volume autometa-data:/data \
  --env-file .env \
  --env AUTOMETA_DATA_DIR=/data \
  --env AUTOMETA_HOST=0.0.0.0 \
  autometa:local
```

The host-side port remains bound to `127.0.0.1`. The container applies pending
SQLite migrations before starting AutoMeta and exposes a local health check at
`/api/v1/health`.

## Review workflow

Every Review uses versioned local artifacts and explicit approval gates:

1. **Review Setup** records the research question and PICO. You can enter PICO
   manually or ask the configured model to draft it.
2. **Search** creates an editable PubMed query, then retrieves and exports real
   PubMed records after Query approval.
3. **Screening** ranks imported or retrieved records with P/I/C/O evidence;
   final study selection remains under researcher control.
4. **Extraction** processes manually uploaded PDFs using researcher-defined
   fields and retains verbatim citations with editable values.
5. **Meta-analysis** creates an editable method plan from manually uploaded CSV
   files and runs it only after explicit Plan approval.

Search offers two explicit generation paths. **Generate query** creates a fast
PICO-based draft. **Generate with retrieval feedback** first retrieves a bounded
PubMed seed set, uses those real records to expand the strategy, and displays
the seed/expanded queries, term changes, and PubMed result-count change. You may
optionally enter known-study PMIDs to display transparent query coverage; this
is user-supplied diagnostic context, not benchmark recall. Both paths save an
editable draft, and only the approved final query is executed downstream.

Editable content is autosaved as a draft. Approving a draft allows downstream
use. Editing an approved upstream artifact revokes its approval and marks every
downstream artifact stale, so outdated results cannot be consumed silently.

Background work is persisted in SQLite and continues if the browser closes
while Uvicorn remains running. Reopening the Review restores its latest job.
After a server restart, unfinished jobs are marked `interrupted`; review the
saved inputs and run the stage again.

## Statistical methods and figures

AutoMeta derives mean differences (MD), standardized mean differences (SMD),
Hedges' g, odds ratios (OR), risk ratios (RR), and risk differences (RD) from
declared arm-level columns. It can also use a reported effect with a 95% CI,
standard error, or variance. Ratio measures are analyzed on the log scale and
back-transformed for presentation; for reported OR/RR inputs, standard errors
and variances are therefore expected on the log scale, while CI endpoints are
entered on the ratio scale. Zero-cell continuity correction is used only when
it is explicitly present in the approved method plan.

Pooling choices are fixed inverse variance, DerSimonian-Laird random effects,
and restricted maximum likelihood (REML) random effects. Results report the
pooled 95% normal-theory CI, Cochran's Q and p-value, I², tau², and tau. A
normal-reference prediction interval is reported for random-effects analyses
with at least three studies. Leave-one-out estimates and subgroup pools call the
same engine with the approved effect scale and model; subgroup analysis requires
a populated subgroup column with at least two groups.

Advanced outputs are explicit plan choices. Forest plots accept at most 100
studies and leave-one-out diagnostics at most 200 studies, preventing accidental
unbounded raster allocation or quadratic refitting on very large uploads.

Invalid inputs or REML non-convergence stop the analysis with an explicit error.
AutoMeta never silently changes the effect measure, source columns, pooling
model, heterogeneity estimator, continuity correction, or subgroup field.

Each successful analysis stores deterministic Review-owned forest plots in SVG,
PNG, and PDF under `data/reviews/<review-id>/figures/`. The result artifact keeps
only file IDs, names, and media types; the files are served through Review-scoped
local endpoints and are included by metadata and hash in the audit export.
End-user calculation and figure generation require Python only. R is not a
runtime dependency; the repository records constructed `metafor` reference
values solely for numeric cross-checking in the test suite.

The generated calculation script reads the corresponding CSV from its own
directory and calls the same `autometa.stats.run_analysis` function used by the
server, so its JSON result can be compared directly with the persisted result
artifact.

## Provenance and reruns

Open **Evidence provenance** from the bottom rail of any Review to inspect its
append-only timeline. AutoMeta records artifact versions, researcher edits,
approvals and revocations, stale transitions, stage runs, failures, and rerun
lineage. The version comparison panel shows deterministic field-level changes
between two saved versions.

A completed workflow event can be rerun from the timeline after confirmation.
The rerun uses the original request and exact historical input versions, then
creates a new job, stage run, output versions, and provenance links. It never
overwrites the source event or its artifacts. Events from older installations
that do not contain a registered operation descriptor remain visible but are
not rerunnable.

**Download audit JSON** exports Review metadata, file metadata and hashes,
artifact versions, approvals, jobs, events, edits, graph edges, and rerun
relationships. It excludes uploaded file contents, local storage paths, and
credentials.

## Privacy and local files

- The API key is read only from `.env` into server memory. It is never accepted
  by the browser, stored in SQLite, or returned by System Status.
- PDFs remain under `data/reviews/<review-id>/uploads/` until the Review is
  permanently deleted.
- CSV datasets remain under `data/reviews/<review-id>/datasets/`.
- Before the first Extraction run, AutoMeta explicitly asks you to acknowledge
  that relevant PDF text passages will be sent to your configured model
  service. The acknowledgement is stored locally.
- Deleting a Review requires its exact name and permanently removes its
  database records and Review directory.
- Binding `AUTOMETA_HOST=0.0.0.0` exposes an unauthenticated local service to
  the network. Use the default `127.0.0.1` unless that exposure is intentional.

## Source-linked PDF evidence

Extraction citations may include parser-verified source metadata: Review file,
page, element type, table index, and bounding box. **View source** opens a
locally bundled PDF.js reader against the Review-owned PDF endpoint. When a
validated bounding box exists AutoMeta highlights it; with page-only metadata
it opens that page beside the quotation; with quotation-only evidence it states
`Exact page location unavailable`. AutoMeta never asks the model to invent page
or coordinate data, and rejects source IDs whose quotation is not present in
the supplied extraction chunk.

## Frontend development

The committed frontend build lets ordinary users run AutoMeta without Node.js.
Contributors changing the interface should use Node.js 20 and start the Python
server first:

```bash
python -m autometa serve
```

In a second terminal, install the locked dependencies and start Vite. Requests
under `/api` are proxied to the default local AutoMeta server at port 8016.

```bash
cd frontend
npm ci
npm run dev
```

Before committing frontend changes, regenerate the packaged assets and run all
frontend checks:

```bash
cd frontend
npm test -- --run
npm run typecheck
npm run build
```

The build writes directly to `autometa/static/`; those generated files are part
of the published Python package and must remain synchronized with the source.

Backend checks run with:

```bash
python -m pytest tests -q
```

The supported product interface starts at 1024 px wide. Phone layouts are not
part of the first release.

## License

AutoMeta is available under the MIT License. See [LICENSE](LICENSE).
