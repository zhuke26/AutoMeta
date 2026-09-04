# AutoMeta

AutoMeta is an early-stage, local, single-user application for assisted
evidence-synthesis workflows. This repository currently records the existing
runtime as a migration baseline while the public application is redesigned.

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

## License

AutoMeta is available under the MIT License. See [LICENSE](LICENSE).
