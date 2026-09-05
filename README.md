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

## Requirements

- Python 3.11 or 3.12
- macOS or Windows for the native CPU installation

GPU acceleration is optional and is not part of the default installation. The
base package does not use a CUDA-specific package index or require a
GPU-specific PyTorch build.

Linux packaging is verified through Docker during release hardening.

## Install

Create and activate a virtual environment, then install AutoMeta:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

On Windows PowerShell, activate the environment with:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
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

The host-side port remains bound to `127.0.0.1`. The container initializes the
local SQLite schema when AutoMeta starts and exposes a local health check at
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

The supported product interface starts at 1024 px wide. Phone layouts are not
part of the first release.

## License

AutoMeta is available under the MIT License. See [LICENSE](LICENSE).
