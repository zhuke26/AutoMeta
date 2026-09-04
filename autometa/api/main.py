"""
AutoMeta FastAPI application entry point.

Start with:
    uvicorn autometa.api.main:app --reload --port 8000

Pages:
    GET  /          → Web UI (autometa/static/index.html)
    GET  /docs      → Swagger UI

API:
    POST /api/v1/search  — PICO → candidate papers
    POST /api/v1/screen  — papers + PICO → inclusion decisions
    GET  /api/v1/health  — health check
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from autometa.api.routers import extraction, meta_analysis, protocol, reviews, screening, search

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("autometa")
API_PREFIX = "/api/v1"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AutoMeta",
    description="Automated Systematic Review — literature search, screening, and data extraction API.",
    version="1.0.0",
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files & root page
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(
        str(STATIC_DIR / "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(protocol.router, prefix=API_PREFIX)
app.include_router(search.router, prefix=API_PREFIX)
app.include_router(screening.router, prefix=API_PREFIX)
app.include_router(extraction.router, prefix=API_PREFIX)
app.include_router(meta_analysis.router, prefix=API_PREFIX)
app.include_router(reviews.router, prefix=API_PREFIX)

# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/health", tags=["utility"])
def health() -> dict[str, str]:
    return {"status": "ok", "product": "AutoMeta"}
