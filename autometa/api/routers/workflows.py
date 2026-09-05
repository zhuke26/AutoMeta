import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder

from autometa.agents.extraction_agent import ExtractionAgent
from autometa.agents.meta_analysis_planner_agent import MetaAnalysisPlannerAgent
from autometa.agents.meta_analysis_runner_agent import MetaAnalysisRunnerAgent
from autometa.agents.protocol_agent import ProtocolAgent
from autometa.agents.screening_agent_v2 import ScreeningAgentV2
from autometa.agents.search_agent import SearchAgent
from autometa.api.dependencies import (
    get_file_storage,
    get_local_settings,
    get_review_service,
    get_workflow_coordinator,
)
from autometa.jobs.manager import JobConflict, JobContext
from autometa.schemas.artifacts import ArtifactView
from autometa.schemas.extraction_models import ExtractionFieldDefinition
from autometa.schemas.jobs import JobView
from autometa.schemas.meta_models import CSVSummary, MetaAnalysisMethodPlan
from autometa.schemas.models import Paper, PICODefinition, StudyDesignFilter
from autometa.schemas.workflows import (
    ExtractionWorkflowRequest,
    MetaPlanWorkflowRequest,
    MetaRunWorkflowRequest,
    ProtocolWorkflowRequest,
    ScreeningRecordsImportRequest,
    ScreeningRunWorkflowRequest,
    SearchQueryWorkflowRequest,
    SearchRunWorkflowRequest,
)
from autometa.services.files import FileStorage, StoredFileNotFound
from autometa.services.reviews import ReviewNotFound, ReviewService
from autometa.services.settings import LocalSettingsService
from autometa.services.workflows import WorkflowCoordinator, WorkflowInputConflict

router = APIRouter(prefix="/reviews/{review_id}/workflow", tags=["workflow"])


def _require_review(review_id: str, reviews: ReviewService) -> None:
    try:
        reviews.get(review_id)
    except ReviewNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Review not found: {review_id}",
        ) from exc


def _submit_or_conflict(
    coordinator: WorkflowCoordinator,
    review_id: str,
    stage: str,
    inputs,
    operation,
) -> JobView:
    try:
        return coordinator.submit(review_id, stage, inputs, operation)
    except (JobConflict, WorkflowInputConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/protocol/draft", response_model=JobView, status_code=202)
def draft_protocol(
    review_id: str,
    request: ProtocolWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
) -> JobView:
    _require_review(review_id, reviews)

    research_question = request.research_question.strip()

    def operation(context: JobContext) -> dict:
        context.emit("drafting", {"message": "Drafting PICO protocol"})
        draft = ProtocolAgent().run(research_question)
        payload = {
            "research_question": research_question,
            **draft.model_dump(),
        }
        artifact = coordinator.artifacts.save_draft(
            review_id,
            "question_pico",
            payload,
        )
        result = {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "version": artifact.version,
        }
        context.emit("artifact_saved", result)
        return result

    return _submit_or_conflict(
        coordinator,
        review_id,
        "protocol",
        [],
        operation,
    )


@router.put("/screening/records", response_model=ArtifactView)
def import_screening_records(
    review_id: str,
    request: ScreeningRecordsImportRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
) -> ArtifactView:
    _require_review(review_id, reviews)
    return coordinator.artifacts.save_draft(
        review_id,
        "records",
        {
            "source": "import",
            "source_format": request.source_format,
            "total_count": len(request.papers),
            "retrieved_count": len(request.papers),
            "papers": [paper.model_dump() for paper in request.papers],
        },
    )


@router.post("/screening/run", response_model=JobView, status_code=202)
def run_screening(
    review_id: str,
    request: ScreeningRunWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
) -> JobView:
    _require_review(review_id, reviews)
    try:
        inputs = coordinator.require_approved(
            review_id,
            ("question_pico", "records"),
        )
        pico = PICODefinition.model_validate(inputs[0].payload.get("pico"))
        raw_papers = inputs[1].payload.get("papers")
        if not isinstance(raw_papers, list) or not raw_papers:
            raise WorkflowInputConflict("Approved Records contain no papers")
        papers = [Paper.model_validate(paper) for paper in raw_papers]
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved Screening inputs are invalid",
        ) from exc

    def operation(context: JobContext) -> dict:
        context.emit(
            "screening",
            {"message": "Ranking records", "total": len(papers)},
        )
        output = ScreeningAgentV2().run_scored_direct(
            papers=papers,
            pico=pico,
            study_design_filter=StudyDesignFilter(request.study_design_filter),
            max_concurrency=request.max_concurrency,
        ).model_dump()
        decisions = output.get("decisions", [])
        output["selected_pmids"] = [
            str(decision.get("pmid"))
            for decision in decisions
            if decision.get("final_decision") in {"INCLUDE", "UNCERTAIN"}
        ]
        artifact = coordinator.artifacts.save_draft(
            review_id,
            "selected_studies",
            output,
        )
        result = {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "version": artifact.version,
        }
        context.emit("artifact_saved", result)
        return result

    return _submit_or_conflict(
        coordinator,
        review_id,
        "screening",
        inputs,
        operation,
    )


@router.post("/search/query", response_model=JobView, status_code=202)
def generate_search_query(
    review_id: str,
    request: SearchQueryWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
) -> JobView:
    _require_review(review_id, reviews)
    try:
        inputs = coordinator.require_approved(review_id, ("question_pico",))
        pico = PICODefinition.model_validate(inputs[0].payload.get("pico"))
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved PICO artifact is invalid",
        ) from exc

    def operation(context: JobContext) -> dict:
        context.emit("planning", {"message": "Generating PubMed query"})
        strategy = SearchAgent().generate_field_tagged_strategy(pico=pico)
        raw_query = strategy.balanced.query.strip()
        if not raw_query:
            raise ValueError("Generated PubMed query is empty")
        artifact = coordinator.artifacts.save_draft(
            review_id,
            "query",
            {
                "strategy_mode": request.strategy_mode,
                "generated_raw_query": raw_query,
                "raw_query": raw_query,
                "strategy": strategy.model_dump(),
            },
        )
        result = {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "version": artifact.version,
        }
        context.emit("artifact_saved", result)
        return result

    return _submit_or_conflict(
        coordinator,
        review_id,
        "search",
        inputs,
        operation,
    )


@router.post("/search/run", response_model=JobView, status_code=202)
def run_search(
    review_id: str,
    request: SearchRunWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
) -> JobView:
    _require_review(review_id, reviews)
    try:
        inputs = coordinator.require_approved(
            review_id,
            ("question_pico", "query"),
        )
        PICODefinition.model_validate(inputs[0].payload.get("pico"))
        raw_query = str(inputs[1].payload.get("raw_query") or "").strip()
        if not raw_query:
            raise WorkflowInputConflict("Approved Query is empty")
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved Search inputs are invalid",
        ) from exc

    def operation(context: JobContext) -> dict:
        context.emit("retrieving", {"message": "Retrieving PubMed records"})
        result = SearchAgent().search_with_raw_query(
            raw_query=raw_query,
            retmax=request.retmax,
            min_year=request.min_year,
            max_year=request.max_year,
            fetch_all=request.fetch_all,
        )
        artifact = coordinator.artifacts.save_draft(
            review_id,
            "records",
            {
                "query_url": result.query_url,
                "total_count": result.total_count,
                "retrieved_count": result.retrieved_count,
                "search_terms": result.search_terms.model_dump(),
                "papers": [paper.model_dump() for paper in result.papers],
                "strategy_mode": "field_tagged_balanced",
                "raw_query": raw_query,
            },
        )
        saved = {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "version": artifact.version,
        }
        context.emit("artifact_saved", saved)
        return saved

    return _submit_or_conflict(
        coordinator,
        review_id,
        "search",
        inputs,
        operation,
    )


@router.post("/extraction/run", response_model=JobView, status_code=202)
def run_extraction(
    review_id: str,
    request: ExtractionWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
    storage: FileStorage = Depends(get_file_storage),
    local_settings: LocalSettingsService = Depends(get_local_settings),
) -> JobView:
    _require_review(review_id, reviews)
    if not local_settings.pdf_disclosure_acknowledged():
        raise HTTPException(
            status_code=409,
            detail=(
                "Confirm that relevant PDF text will be sent to the configured "
                "model service before starting Extraction"
            ),
        )
    try:
        inputs = coordinator.require_approved(review_id, ("question_pico",))
        pico = PICODefinition.model_validate(inputs[0].payload.get("pico"))
        records = []
        for file_id in request.file_ids:
            record = storage.get(file_id)
            if record.review_id != review_id:
                raise WorkflowInputConflict("PDF does not belong to this Review")
            if record.mime_type != "application/pdf":
                raise WorkflowInputConflict("Extraction accepts PDF files only")
            records.append(record)
    except StoredFileNotFound as exc:
        raise HTTPException(status_code=409, detail=f"PDF not found: {exc}") from exc
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved Extraction inputs are invalid",
        ) from exc

    characteristic_fields = [
        ExtractionFieldDefinition.model_validate(field.model_dump())
        for field in request.study_characteristics_fields
    ]
    result_fields = [
        ExtractionFieldDefinition.model_validate(field.model_dump())
        for field in request.study_results_fields
    ]

    def operation(context: JobContext) -> dict:
        context.emit("parsing", {"message": "Parsing locally stored PDFs"})
        paths = [str(storage.resolve(record)) for record in records]
        context.emit(
            "extracting",
            {"message": "Sending relevant PDF text to the configured model service"},
        )
        output = ExtractionAgent().run(
            file_paths=paths,
            pico=pico,
            char_fields=characteristic_fields,
            result_fields=result_fields,
            top_k=request.top_k,
            max_concurrency=request.max_concurrency,
        )
        artifact = coordinator.artifacts.save_draft(
            review_id,
            "sources",
            {
                **output.model_dump(),
                "file_ids": [record.id for record in records],
                "study_characteristics_fields": [
                    field.model_dump() for field in characteristic_fields
                ],
                "study_results_fields": [field.model_dump() for field in result_fields],
            },
        )
        result = {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "version": artifact.version,
        }
        context.emit("artifact_saved", result)
        return result

    return _submit_or_conflict(
        coordinator,
        review_id,
        "extraction",
        inputs,
        operation,
    )


def _review_datasets(
    review_id: str,
    file_ids: list[str],
    storage: FileStorage,
):
    records = []
    for file_id in file_ids:
        try:
            record = storage.get(file_id)
        except StoredFileNotFound as exc:
            raise WorkflowInputConflict(f"Dataset not found: {file_id}") from exc
        if record.review_id != review_id:
            raise WorkflowInputConflict("Dataset does not belong to this Review")
        if record.kind != "csv":
            raise WorkflowInputConflict("Meta-analysis accepts CSV datasets only")
        records.append(record)
    return records


@router.post("/meta/plan", response_model=JobView, status_code=202)
def plan_meta_analysis(
    review_id: str,
    request: MetaPlanWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
    storage: FileStorage = Depends(get_file_storage),
) -> JobView:
    _require_review(review_id, reviews)
    try:
        inputs = coordinator.require_approved(review_id, ("question_pico",))
        pico = PICODefinition.model_validate(inputs[0].payload.get("pico"))
        records = _review_datasets(review_id, request.file_ids, storage)
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved Meta-analysis inputs are invalid",
        ) from exc

    def operation(context: JobContext) -> dict:
        context.emit("planning", {"message": "Validating CSV datasets"})
        summaries: list[CSVSummary] = []
        for record in records:
            frame = pd.read_csv(storage.resolve(record), encoding="utf-8-sig")
            if frame.empty:
                raise ValueError(f"CSV dataset has no data rows: {record.original_name}")
            head = frame.head(request.sample_rows)
            sample = head.astype(object).where(pd.notnull(head), None)
            summaries.append(CSVSummary(
                csv_file=record.original_name,
                columns=[str(column) for column in frame.columns],
                row_count=int(len(frame)),
                sample_rows=sample.to_dict(orient="records"),
            ))
        response = MetaAnalysisPlannerAgent().run(
            pico=pico,
            csv_summaries=summaries,
            user_hint=request.user_hint,
            max_concurrency=request.max_concurrency,
        )
        raw = response.model_dump()
        plans = [
            MetaAnalysisMethodPlan.model_validate(plan)
            for plan in raw.get("plans", [])
        ]
        expected = {record.original_name for record in records}
        actual = {plan.csv_file for plan in plans}
        if actual != expected:
            raise ValueError("Planner must return exactly one plan for each CSV dataset")
        artifact = coordinator.artifacts.save_draft(
            review_id,
            "plan",
            jsonable_encoder({
                "file_ids": [record.id for record in records],
                "user_hint": request.user_hint,
                "csv_summaries": [summary.model_dump() for summary in summaries],
                "plans": [plan.model_dump() for plan in plans],
            }),
        )
        result = {
            "artifact_id": artifact.artifact_id,
            "kind": artifact.kind,
            "version": artifact.version,
        }
        context.emit("artifact_saved", result)
        return result

    return _submit_or_conflict(
        coordinator,
        review_id,
        "meta_analysis",
        inputs,
        operation,
    )


@router.post("/meta/run", response_model=JobView, status_code=202)
def run_meta_analysis(
    review_id: str,
    _request: MetaRunWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
    storage: FileStorage = Depends(get_file_storage),
) -> JobView:
    _require_review(review_id, reviews)
    try:
        inputs = coordinator.require_approved(review_id, ("plan",))
        plan_payload = inputs[0].payload
        raw_file_ids = plan_payload.get("file_ids")
        raw_plans = plan_payload.get("plans")
        if not isinstance(raw_file_ids, list) or not isinstance(raw_plans, list):
            raise WorkflowInputConflict("Approved Plan is missing datasets or methods")
        records = _review_datasets(
            review_id,
            [str(file_id) for file_id in raw_file_ids],
            storage,
        )
        plans = [MetaAnalysisMethodPlan.model_validate(plan) for plan in raw_plans]
        available = {record.original_name for record in records}
        if {plan.csv_file for plan in plans} != available:
            raise WorkflowInputConflict(
                "Approved Plan does not match the stored CSV datasets"
            )
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Approved Plan is invalid") from exc

    def operation(context: JobContext) -> dict:
        context.emit(
            "analyzing",
            {"message": "Validating and fitting meta-analysis models"},
        )
        frames = {
            record.original_name: pd.read_csv(
                storage.resolve(record),
                encoding="utf-8-sig",
            )
            for record in records
        }
        response = MetaAnalysisRunnerAgent().run(plans=plans, csv_frames=frames)
        raw = jsonable_encoder(response.model_dump())
        results = raw.get("results", [])
        if len(results) != len(plans):
            raise ValueError("Meta-analysis did not return one result per approved plan")
        for plan, result in zip(plans, results):
            if plan.output.include_pooled_effect and result.get("pooled_effect") is None:
                details = "; ".join(result.get("warnings", []))
                raise ValueError(
                    f"Analysis failed for {plan.csv_file}: "
                    f"{details or 'pooled effect unavailable'}"
                )
        saved = coordinator.artifacts.save_drafts(
            review_id,
            {
                "code": {"generated_code": raw.get("generated_code", {})},
                "result": {"results": results},
            },
        )
        result_reference = {
            "code_artifact_id": saved["code"].artifact_id,
            "result_artifact_id": saved["result"].artifact_id,
        }
        context.emit("artifact_saved", result_reference)
        return result_reference

    return _submit_or_conflict(
        coordinator,
        review_id,
        "meta_analysis",
        inputs,
        operation,
    )
