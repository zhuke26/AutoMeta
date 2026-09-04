from fastapi import APIRouter, Depends, HTTPException

from autometa.agents.protocol_agent import ProtocolAgent
from autometa.agents.search_agent import SearchAgent
from autometa.agents.screening_agent_v2 import ScreeningAgentV2
from autometa.api.dependencies import get_review_service, get_workflow_coordinator
from autometa.jobs.manager import JobConflict, JobContext
from autometa.schemas.jobs import JobView
from autometa.schemas.artifacts import ArtifactView
from autometa.schemas.models import PICODefinition, Paper, StudyDesignFilter
from autometa.schemas.workflows import (
    ProtocolWorkflowRequest,
    ScreeningRecordsImportRequest,
    ScreeningRunWorkflowRequest,
    SearchQueryWorkflowRequest,
    SearchRunWorkflowRequest,
)
from autometa.services.reviews import ReviewNotFound, ReviewService
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
        pico = PICODefinition.model_validate(inputs[0].payload.get("pico"))
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
