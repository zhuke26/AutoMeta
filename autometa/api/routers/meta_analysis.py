import logging
from typing import List

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from autometa.agents.meta_analysis_planner_agent import MetaAnalysisPlannerAgent
from autometa.agents.meta_analysis_runner_agent import MetaAnalysisRunnerAgent
from autometa.schemas.meta_models import CSVSummary, MetaAnalysisMethodPlan
from autometa.schemas.models import PICODefinition

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meta", tags=["meta-analysis"])


class MetaAnalysisPlanMetadata(BaseModel):
    pico: PICODefinition
    user_hint: str = Field(default="")
    sample_rows: int = Field(default=5, ge=1, le=20)
    max_concurrency: int = Field(default=1, ge=1, le=5)


class MetaAnalysisRunMetadata(BaseModel):
    pico: PICODefinition
    plans: List[MetaAnalysisMethodPlan]


async def _read_csv_upload(file: UploadFile) -> pd.DataFrame:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail=f"Not a CSV file: {file.filename}")

    try:
        content = await file.read()
        if not content:
            raise ValueError("empty file")
        from io import BytesIO

        return pd.read_csv(BytesIO(content), encoding="utf-8-sig")
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to read CSV file {file.filename}: {exc}",
        ) from exc


async def _summarize_csv(file: UploadFile, sample_rows: int) -> CSVSummary:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail=f"Not a CSV file: {file.filename}")

    df = await _read_csv_upload(file)

    sample_df = df.head(sample_rows)
    sample = sample_df.where(pd.notnull(sample_df), None).to_dict(orient="records")
    return CSVSummary(
        csv_file=file.filename,
        columns=[str(col) for col in df.columns],
        row_count=int(len(df)),
        sample_rows=sample,
    )


@router.post(
    "/plan", summary="Generate meta-analysis method plans from cleaned CSV files"
)
async def plan_meta_analysis(
    files: List[UploadFile] = File(
        ..., description="Cleaned CSV files, one per meta-analysis dataset"
    ),
    metadata: str = Form(
        ..., description="JSON string with pico and optional user_hint"
    ),
):
    try:
        meta = MetaAnalysisPlanMetadata.model_validate_json(metadata)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid metadata JSON: {exc}"
        ) from exc

    if not files:
        raise HTTPException(status_code=422, detail="At least one CSV file is required")

    logger.info("POST /api/v1/meta/plan files=%d", len(files))

    csv_summaries = []
    for file in files:
        csv_summaries.append(await _summarize_csv(file, meta.sample_rows))

    try:
        agent = MetaAnalysisPlannerAgent()
        response = agent.run(
            pico=meta.pico,
            csv_summaries=csv_summaries,
            user_hint=meta.user_hint,
            max_concurrency=meta.max_concurrency,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("MetaAnalysisPlannerAgent failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return response.model_dump()


@router.post(
    "/run", summary="Run meta-analysis calculations from confirmed method plans"
)
async def run_meta_analysis(
    files: List[UploadFile] = File(
        ..., description="CSV files referenced by the confirmed method plans"
    ),
    metadata: str = Form(..., description="JSON string with pico and confirmed plans"),
):
    try:
        meta = MetaAnalysisRunMetadata.model_validate_json(metadata)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid metadata JSON: {exc}"
        ) from exc

    if not meta.plans:
        raise HTTPException(
            status_code=422, detail="At least one meta-analysis plan is required"
        )

    logger.info("POST /api/v1/meta/run files=%d plans=%d", len(files), len(meta.plans))

    csv_frames = {}
    for file in files:
        if not file.filename:
            continue
        csv_frames[file.filename] = await _read_csv_upload(file)

    try:
        agent = MetaAnalysisRunnerAgent()
        response = agent.run(plans=meta.plans, csv_frames=csv_frames)
    except Exception as exc:
        logger.exception("MetaAnalysisRunnerAgent failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return response.model_dump()
