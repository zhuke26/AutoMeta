# AutoMeta Phase 1A Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a safe, installable, cross-platform AutoMeta repository; remove the legacy product/package identity; introduce OpenAI-compatible configuration; and keep the current web workflow runnable before persistence and React migration begin.

**Architecture:** Consolidate the current backend and agents into one `autometa` Python package, expose versioned FastAPI routes, and add a Python entry point that starts Uvicorn from environment-backed settings. Preserve the current static UI temporarily as a regression surface; the React application replaces it in a later plan.

**Tech Stack:** Python 3.11/3.12, FastAPI, Uvicorn, Pydantic Settings, OpenAI-compatible Python client, pytest, SQLite-ready filesystem layout, GitHub Actions.

## Global Constraints

- The product and runtime package name is `AutoMeta` / `autometa`; legacy names must not remain in the completed public runtime tree.
- Local, single-user deployment only; no authentication or multi-user permissions.
- Default bind address is `127.0.0.1`; `0.0.0.0` requires explicit configuration and a warning.
- API keys remain in `.env` and server memory only and must be redacted from output and logs.
- Python 3.11 and 3.12 are supported; macOS and Windows CPU installs are verified.
- Linux support is provided through Docker in the release-hardening plan.
- No manuscript, paper-figure, benchmark, evaluation, or user-generated data enters the public runtime repository.
- No user-facing example dataset is shipped.
- The committed frontend build remains runnable without Node.js; the React build is introduced in a later plan.
- New behavior and refactors follow red-green-refactor TDD.

---

## Plan Series

This is the first of five Phase 1 plans:

1. Phase 1A — repository boundary, package rename, configuration, CLI, and API baseline.
2. Phase 1B — SQLite Review/Library persistence, file storage, approvals, and persistent jobs.
3. Phase 1C — React/Vite design system, Logo A, Review creation, and Library UI.
4. Phase 1D — Search, Screening, Extraction, and Meta-analysis UI/API migration.
5. Phase 1E — cross-platform packaging, browser verification, documentation, and release gate.

Each plan must leave the application runnable and independently testable.

### Task 1: Establish the public repository boundary

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `LICENSE`
- Create: `README.md`
- Create: `tests/foundation/test_repository_policy.py`
- Modify: `pyproject.toml` later in Task 5

**Interfaces:**
- Consumes: the approved design at `docs/superpowers/specs/2026-09-05-autometa-web-application-redesign.md`.
- Produces: a safe Git boundary and `assert_public_tree_policy(root: Path) -> None` test contract used by release checks.

- [ ] **Step 1: Write the failing repository-policy test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_private_workspace_paths_are_gitignored() -> None:
    ignore_file = ROOT / ".gitignore"
    assert ignore_file.exists()
    text = ignore_file.read_text(encoding="utf-8")
    required = {
        ".env",
        "data/",
        "runs/",
        "logs/",
        "tmp/",
        "paper_figures/",
        "baselines/",
        "docling_models/",
        "backups/",
        "*.docx",
        "node_modules/",
    }
    assert required <= set(text.splitlines())


def test_public_metadata_files_exist() -> None:
    for relative in ("README.md", ".env.example", "LICENSE"):
        assert (ROOT / relative).is_file(), relative
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python -m pytest tests/foundation/test_repository_policy.py -v
```

Expected: FAIL because `.gitignore`, `.env.example`, `LICENSE`, and `README.md` do not yet exist.

- [ ] **Step 3: Create the repository-policy files**

Create `.gitignore` with these exact required entries and standard language/tool exclusions:

```gitignore
.env
.env.*
!.env.example
data/
runs/
logs/
tmp/
paper_figures/
baselines/
docling_models/
backups/
reference/
参考文献/
*.docx
~$*.docx
*.pdf
AutoMeta主图.png
_v1/
.uploads/
.trae-html-share-packages/
.claude/
.vscode/
.DS_Store
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
.venv/
venv/
node_modules/
frontend/.vite/
frontend/coverage/
```

Create `.env.example`:

```dotenv
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
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

Create `LICENSE` with the standard MIT License and:

```text
Copyright (c) 2026 AutoMeta Contributors
```

Create an English `README.md` that identifies the repository as an early local,
single-user AutoMeta application, documents that no sample dataset is shipped,
and points to the design specification. Do not document unimplemented React,
Library, provenance, or advanced statistics as available features.

- [ ] **Step 4: Run policy tests and Git ignore checks**

Run:

```bash
python -m pytest tests/foundation/test_repository_policy.py -v
git check-ignore .env runs paper_figures baselines docling_models backups AutoMeta_JMIR.docx
```

Expected: 2 tests PASS; every private path is printed by `git check-ignore`.

- [ ] **Step 5: Record the current runtime source as the migration baseline**

Run:

```bash
legacy_package="auto""sr"
git add .gitignore .env.example LICENSE README.md \
  app "$legacy_package" configs requirements.txt run_local.sh \
  tests/foundation/test_repository_policy.py \
  docs/superpowers/specs docs/superpowers/plans
git diff --cached --check
git commit -m "chore: establish AutoMeta repository boundary"
```

Expected: the commit contains runtime source and approved documentation but no
credential, manuscript, benchmark, run output, model weight, or uploaded file.

### Task 2: Consolidate runtime code into the `autometa` package

**Files:**
- Create: `tests/foundation/test_package_identity.py`
- Move: the legacy agent package tree to `autometa/**`
- Move: `app/main.py` to `autometa/api/main.py`
- Move: `app/routers/**` to `autometa/api/routers/**`
- Move: `app/static/**` to `autometa/static/**`
- Move: `configs/settings.py` to `autometa/config.py`
- Create: `autometa/api/__init__.py`
- Delete after moves: `app/__init__.py`, `configs/__init__.py`
- Modify: all moved Python imports

**Interfaces:**
- Consumes: existing agent, schema, router, and static-UI behavior.
- Produces: importable `autometa`, `autometa.api.main:app`, and a runtime tree with no legacy package references.

- [ ] **Step 1: Write the failing package-identity tests**

```python
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_autometa_api_is_importable() -> None:
    module = importlib.import_module("autometa.api.main")
    assert module.app.title == "AutoMeta"


def test_runtime_tree_contains_no_legacy_identity() -> None:
    forbidden = ("Auto" + "SR", "auto" + "sr")
    roots = [ROOT / "autometa", ROOT / "README.md", ROOT / "run_local.sh"]
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if path.is_file() and path.suffix in {".py", ".html", ".md", ".sh"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                assert not any(token in text for token in forbidden), str(path)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python -m pytest tests/foundation/test_package_identity.py -v
```

Expected: FAIL because `autometa.api.main` does not exist.

- [ ] **Step 3: Move the packages without changing behavior**

Run the directory moves as one mechanical migration:

```bash
legacy_package="auto""sr"
git mv "$legacy_package" autometa
mkdir -p autometa/api
git mv app/main.py autometa/api/main.py
git mv app/routers autometa/api/routers
git mv app/static autometa/static
git mv configs/settings.py autometa/config.py
git rm app/__init__.py configs/__init__.py
```

Use repository-wide, scoped import changes in tracked runtime files:

```text
from <legacy-package>...  -> from autometa...
import <legacy-package>... -> import autometa...
from configs.settings...  -> from autometa.config...
from app.routers...        -> from autometa.api.routers...
```

Create `autometa/api/__init__.py` with `apply_patch` rather than a shell write
shortcut. Update `autometa/api/main.py` so `STATIC_DIR` resolves to
`Path(__file__).resolve().parents[1] / "static"`, set the FastAPI title to
`AutoMeta`, and remove the missing benchmark-example endpoint and data path.
Remove the `Load Example` button and its unused modal/functions from the
temporary static UI so the interim application has no dead control.

- [ ] **Step 4: Run identity and import tests**

Run:

```bash
python -m pytest tests/foundation/test_package_identity.py -v
python -c "from autometa.api.main import app; print(app.title)"
rg -n -i "auto""sr" autometa README.md run_local.sh
```

Expected: tests PASS, import prints `AutoMeta`, and the final search reports no
runtime references. When executing the plan, replace the deliberately neutral
search marker with the two legacy spellings assembled in the test so the plan
document itself does not reintroduce them.

- [ ] **Step 5: Commit the package migration**

```bash
git add autometa tests/foundation app configs README.md run_local.sh
git diff --cached --check
git commit -m "refactor: consolidate runtime under autometa package"
```

### Task 3: Introduce typed OpenAI-compatible settings

**Files:**
- Create: `tests/foundation/test_settings.py`
- Modify: `autometa/config.py`
- Modify: `autometa/agents/protocol_agent.py`
- Modify: `autometa/agents/search_agent.py`
- Modify: `autometa/agents/screening_agent_v2.py`
- Modify: `autometa/agents/extraction_agent.py`
- Modify: `autometa/agents/meta_analysis_planner_agent.py`
- Modify: `autometa/tools/llm.py`

**Interfaces:**
- Produces: `Settings.model_for(stage: AgentStage) -> str`, `get_settings() -> Settings`, and server-only `SecretStr` credentials.
- Consumes: OpenAI-compatible `base_url`, API key, and model names from environment variables.

- [ ] **Step 1: Write failing settings tests**

```python
from autometa.config import AgentStage, Settings


def test_stage_model_uses_global_default() -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key="secret",
        llm_base_url="https://example.test/v1",
        llm_model="general-model",
    )
    assert settings.model_for(AgentStage.SEARCH) == "general-model"


def test_stage_model_override_wins() -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key="secret",
        llm_base_url="https://example.test/v1",
        llm_model="general-model",
        extraction_model="extract-model",
    )
    assert settings.model_for(AgentStage.EXTRACTION) == "extract-model"


def test_secret_is_redacted_from_serialized_settings() -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key="do-not-expose",
        llm_base_url="https://example.test/v1",
        llm_model="general-model",
    )
    assert "do-not-expose" not in str(settings.safe_summary())
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python -m pytest tests/foundation/test_settings.py -v
```

Expected: FAIL because `AgentStage` and the typed settings interface do not exist.

- [ ] **Step 3: Implement typed settings**

Implement this public shape in `autometa/config.py`:

```python
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentStage(StrEnum):
    PROTOCOL = "protocol"
    SEARCH = "search"
    SCREENING = "screening"
    EXTRACTION = "extraction"
    META_ANALYSIS = "meta_analysis"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    protocol_model: str = ""
    search_model: str = ""
    screening_model: str = ""
    extraction_model: str = ""
    meta_analysis_model: str = ""
    pubmed_api_key: SecretStr = SecretStr("")
    autometa_data_dir: Path = Path("data")
    autometa_host: str = "127.0.0.1"
    autometa_port: int = Field(default=8016, ge=1, le=65535)

    def model_for(self, stage: AgentStage) -> str:
        override = {
            AgentStage.PROTOCOL: self.protocol_model,
            AgentStage.SEARCH: self.search_model,
            AgentStage.SCREENING: self.screening_model,
            AgentStage.EXTRACTION: self.extraction_model,
            AgentStage.META_ANALYSIS: self.meta_analysis_model,
        }[stage]
        return override or self.llm_model

    def safe_summary(self) -> dict[str, object]:
        return {
            "base_url": self.llm_base_url,
            "default_model": self.llm_model,
            "data_dir": str(self.autometa_data_dir),
            "host": self.autometa_host,
            "port": self.autometa_port,
            "api_key_configured": bool(self.llm_api_key.get_secret_value()),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

Update every agent to request its stage model through `get_settings().model_for(...)`.
Update `autometa/tools/llm.py` to construct the OpenAI client from
`llm_api_key` and `llm_base_url`. Remove provider-specific environment names
and key-pool assumptions from the public runtime.

- [ ] **Step 4: Verify GREEN and scan for secret exposure**

Run:

```bash
python -m pytest tests/foundation/test_settings.py -v
rg -n 'API_KEY|api_key' autometa | rg -v 'SecretStr|configured|get_secret_value|Field|test'
```

Expected: tests PASS; the review of remaining matches confirms no endpoint,
schema, or log serializes a raw key.

- [ ] **Step 5: Commit provider-neutral configuration**

```bash
git add autometa/config.py autometa/agents autometa/tools/llm.py tests/foundation/test_settings.py .env.example
git diff --cached --check
git commit -m "feat: add OpenAI-compatible model configuration"
```

### Task 4: Add the cross-platform Uvicorn entry point

**Files:**
- Create: `tests/foundation/test_cli.py`
- Create: `autometa/cli.py`
- Create: `autometa/__main__.py`
- Delete: `run_local.sh`
- Modify: `README.md`

**Interfaces:**
- Produces: `autometa.cli.serve() -> None`, `autometa.cli.build_uvicorn_options(settings: Settings) -> dict[str, object]`, and `python -m autometa serve`.
- Consumes: `get_settings()` and `autometa.api.main:app`.

- [ ] **Step 1: Write the failing CLI tests**

```python
from autometa.cli import build_uvicorn_options
from autometa.config import Settings


def test_uvicorn_defaults_are_local_only() -> None:
    options = build_uvicorn_options(Settings(llm_model="test-model"))
    assert options == {"host": "127.0.0.1", "port": 8016}


def test_lan_binding_is_explicit() -> None:
    options = build_uvicorn_options(
        Settings(llm_model="test-model", autometa_host="0.0.0.0", autometa_port=9000)
    )
    assert options == {"host": "0.0.0.0", "port": 9000}
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python -m pytest tests/foundation/test_cli.py -v
```

Expected: FAIL because `autometa.cli` does not exist.

- [ ] **Step 3: Implement the CLI**

Implement `autometa/cli.py` as:

```python
from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

import uvicorn

from autometa.config import Settings, get_settings


LOGGER = logging.getLogger(__name__)


def build_uvicorn_options(settings: Settings) -> dict[str, object]:
    return {"host": settings.autometa_host, "port": settings.autometa_port}


def serve() -> None:
    settings = get_settings()
    options = build_uvicorn_options(settings)
    if options["host"] not in {"127.0.0.1", "::1", "localhost"}:
        LOGGER.warning(
            "AutoMeta is listening beyond localhost without authentication."
        )
    uvicorn.run("autometa.api.main:app", reload=False, **options)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autometa")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Start the local AutoMeta Uvicorn server")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        serve()
```

Implement `autometa/__main__.py` as:

```python
from autometa.cli import main


if __name__ == "__main__":
    main()
```

Remove the Bash-only
startup script after the Python entry point passes tests. Document equivalent
macOS and Windows commands:

```bash
python -m autometa serve
```

```powershell
python -m autometa serve
```

- [ ] **Step 4: Run CLI and import verification**

Run:

```bash
python -m pytest tests/foundation/test_cli.py -v
python -m autometa --help
python -m autometa serve --help
```

Expected: tests PASS; help exits 0 and documents the `serve` command.

- [ ] **Step 5: Commit the cross-platform entry point**

```bash
git add autometa/cli.py autometa/__main__.py tests/foundation/test_cli.py README.md run_local.sh
git diff --cached --check
git commit -m "feat: add cross-platform AutoMeta server command"
```

### Task 5: Create installable CPU-first Python packaging

**Files:**
- Create: `pyproject.toml`
- Create: `tests/foundation/test_packaging.py`
- Delete: `requirements.txt`
- Modify: `README.md`

**Interfaces:**
- Produces: installable `autometa` package, `autometa` console command, `dev` optional dependency group, and platform-neutral dependency resolution.
- Consumes: the package layout and CLI from Tasks 2–4.

- [ ] **Step 1: Write the failing packaging test**

```python
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_exposes_autometa_command_without_cuda_index() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == ">=3.11,<3.13"
    assert data["project"]["scripts"]["autometa"] == "autometa.cli:main"
    serialized = str(data).lower()
    assert "cu128" not in serialized
    assert "extra-index-url" not in serialized
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python -m pytest tests/foundation/test_packaging.py -v
```

Expected: FAIL because `pyproject.toml` does not exist.

- [ ] **Step 3: Add `pyproject.toml`**

Define:

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "autometa"
version = "0.1.0"
description = "Researcher-supervised evidence synthesis workspace"
readme = "README.md"
requires-python = ">=3.11,<3.13"
license = { file = "LICENSE" }
dependencies = [
  "beautifulsoup4>=4.11",
  "docling>=2.0",
  "fastapi>=0.115",
  "httpx>=0.27",
  "lxml>=4.9",
  "numpy>=1.26",
  "openai>=1.0",
  "pandas>=2.1",
  "pydantic>=2.8",
  "pydantic-settings>=2.4",
  "python-multipart>=0.0.9",
  "rank-bm25>=0.2.2",
  "requests>=2.31",
  "scipy>=1.12",
  "tenacity>=8.2",
  "uvicorn[standard]>=0.30",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov>=5.0",
  "ruff>=0.6",
]

[project.scripts]
autometa = "autometa.cli:main"

[tool.setuptools.packages.find]
include = ["autometa*"]

[tool.setuptools.package-data]
autometa = ["static/**/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Do not specify a CUDA wheel index or GPU-specific torchvision build. Document
that the default path is CPU-compatible and that optional GPU setup is an
advanced, separately maintained path.

- [ ] **Step 4: Build and test in a clean virtual environment**

Run on macOS first:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest tests/foundation -v
.venv/bin/python -c "from autometa.api.main import app; print(app.title)"
```

Expected: installation succeeds without a CUDA index, tests PASS, and import
prints `AutoMeta`. The Windows CI task in Task 7 repeats the installation with
the Windows virtual-environment interpreter.

- [ ] **Step 5: Commit packaging**

```bash
git add pyproject.toml README.md tests/foundation/test_packaging.py requirements.txt
git diff --cached --check
git commit -m "build: add CPU-first Python packaging"
```

### Task 6: Version the API and preserve current UI behavior

**Files:**
- Create: `tests/api/test_health.py`
- Create: `tests/api/test_spa.py`
- Modify: `autometa/api/main.py`
- Modify: `autometa/api/routers/protocol.py`
- Modify: `autometa/api/routers/search.py`
- Modify: `autometa/api/routers/screening.py`
- Modify: `autometa/api/routers/extraction.py`
- Modify: `autometa/api/routers/meta_analysis.py`
- Modify: `autometa/static/index.html`

**Interfaces:**
- Produces: `/api/v1/health`, `/api/v1/protocol`, `/api/v1/search`, `/api/v1/screen`, `/api/v1/extract`, and `/api/v1/meta` route families.
- Consumes: unchanged request and response payloads from the existing endpoints.

- [ ] **Step 1: Write failing API and SPA tests**

```python
from fastapi.testclient import TestClient

from autometa.api.main import app


client = TestClient(app)


def test_versioned_health_endpoint() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "product": "AutoMeta"}


def test_root_serves_autometa_spa() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "AutoMeta" in response.text
    assert "Load Example" not in response.text
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/api/test_health.py tests/api/test_spa.py -v
```

Expected: health test FAILS on the old path or response; SPA test FAILS while
the obsolete example control remains.

- [ ] **Step 3: Add the `/api/v1` prefix and update the temporary SPA**

Define `API_PREFIX = "/api/v1"` in `autometa/api/main.py`. Change the individual
router prefixes from `/api/<resource>` to `/<resource>`, register each router
with `app.include_router(router, prefix=API_PREFIX)`, and expose health with:

```python
@app.get(f"{API_PREFIX}/health", tags=["utility"])
def health() -> dict[str, str]:
    return {"status": "ok", "product": "AutoMeta"}
```

Update every fetch call in
the temporary static UI from `/api/...` to `/api/v1/...`. Remove the benchmark
modal, benchmark fetch, and `Load Example` action.

Keep request and response bodies otherwise unchanged so this task does not
combine API versioning with workflow redesign.

- [ ] **Step 4: Run API and existing foundation tests**

```bash
python -m pytest tests/api tests/foundation -v
python -m autometa serve
```

In a second terminal:

```bash
curl -fsS http://127.0.0.1:8016/api/v1/health
curl -fsS http://127.0.0.1:8016/ | python -c "import sys; assert 'AutoMeta' in sys.stdin.read()"
```

Expected: tests PASS; health returns `{"status":"ok","product":"AutoMeta"}`;
the existing workflow page loads without the nonfunctional example control.

- [ ] **Step 5: Commit API versioning**

```bash
git add autometa/api autometa/static/index.html tests/api
git diff --cached --check
git commit -m "refactor: version AutoMeta API routes"
```

### Task 7: Add macOS and Windows foundation CI

**Files:**
- Create: `.github/workflows/foundation.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: installable package and foundation/API tests.
- Produces: macOS and Windows CPU verification for Python 3.11 and 3.12.

- [ ] **Step 1: Add the CI workflow**

Create `.github/workflows/foundation.yml` with:

```yaml
name: foundation

on:
  push:
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [macos-latest, windows-latest]
        python-version: ["3.11", "3.12"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - name: Install AutoMeta
        run: python -m pip install -e ".[dev]"
      - name: Run foundation tests
        run: python -m pytest tests/foundation tests/api -v
      - name: Verify application import
        run: python -c "from autometa.api.main import app; assert app.title == 'AutoMeta'"
```

- [ ] **Step 2: Validate the workflow and local suite**

Run:

```bash
python -m pytest tests/foundation tests/api -v
python -m compileall -q autometa tests
git diff --check
```

Expected: all tests PASS, compilation succeeds, and Git reports no whitespace
errors.

- [ ] **Step 3: Commit CI**

```bash
git add .github/workflows/foundation.yml README.md
git diff --cached --check
git commit -m "ci: verify AutoMeta foundation on macOS and Windows"
```

### Task 8: Phase 1A release gate

**Files:**
- Modify if verification exposes a defect: only files already listed in Tasks 1–7
- Test: `tests/foundation/**`
- Test: `tests/api/**`

**Interfaces:**
- Consumes: all Phase 1A deliverables.
- Produces: a tagged internal foundation checkpoint suitable for starting the SQLite/Library plan.

- [ ] **Step 1: Run the complete foundation gate**

```bash
python -m pytest tests/foundation tests/api -v
python -m compileall -q autometa tests
git diff --check
git status --short
```

Expected: tests PASS, compilation succeeds, no whitespace errors are reported,
and only intentionally untracked private workspace files remain ignored.

- [ ] **Step 2: Verify runtime identity and secret boundaries**

```bash
python -m autometa --help
python -c "from autometa.config import get_settings; print(get_settings().safe_summary())"
git ls-files | rg '(^|/)(\.env|runs|paper_figures|baselines|docling_models|backups)(/|$)|\.docx$|\.pdf$' && exit 1 || true
```

Expected: help identifies AutoMeta, the settings summary contains no secret,
and no private asset path is tracked.

- [ ] **Step 3: Start the server and perform the smoke check**

```bash
python -m autometa serve
```

In a second terminal:

```bash
curl -fsS http://127.0.0.1:8016/api/v1/health
```

Expected: the response is `{"status":"ok","product":"AutoMeta"}` and the
current workflow UI is available at `http://127.0.0.1:8016/`.

- [ ] **Step 4: Commit any verification-only fixes**

If verification required changes, rerun the full gate and commit only those
fixes:

```bash
git add autometa tests README.md pyproject.toml .github .env.example .gitignore LICENSE
git diff --cached --check
git commit -m "fix: complete AutoMeta foundation verification"
```

If no changes were required, do not create an empty commit.

## Phase 1A Completion Criteria

- AutoMeta is an independent repository with private and research artifacts ignored.
- The runtime package and product identity are AutoMeta throughout.
- The current working web workflow remains available.
- API routes are versioned under `/api/v1`.
- Configuration is provider-neutral and never exposes API keys.
- `python -m autometa serve` starts Uvicorn on localhost by default.
- Python packaging contains no CUDA-only index or wheel requirement.
- macOS and Windows CPU foundation checks are represented in CI.
- The Phase 1B SQLite/Library plan can proceed without another package migration.
