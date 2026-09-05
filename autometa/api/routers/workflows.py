from fastapi import APIRouter, Depends, HTTPException

from autometa.api.dependencies import (
    get_file_storage,
    get_local_settings,
    get_review_service,
    get_workflow_coordinator,
    get_workflow_operations,
)
from autometa.jobs.manager import JobConflict
from autometa.schemas.artifacts import ArtifactView
from autometa.schemas.jobs import JobView
from autometa.schemas.meta_models import MetaAnalysisMethodPlan
from autometa.schemas.models import Paper, PICODefinition
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
from autometa.services.workflow_operations import WorkflowOperationRegistry
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
    *,
    operation_kind: str,
    request_payload: dict,
) -> JobView:
    try:
        return coordinator.submit(
            review_id,
            stage,
            inputs,
            operation,
            operation_kind=operation_kind,
            request_payload=request_payload,
        )
    except (JobConflict, WorkflowInputConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/protocol/draft", response_model=JobView, status_code=202)
def draft_protocol(
    review_id: str,
    request: ProtocolWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    operations: WorkflowOperationRegistry = Depends(get_workflow_operations),
    reviews: ReviewService = Depends(get_review_service),
) -> JobView:
    _require_review(review_id, reviews)
    request_payload = request.model_dump(mode="json")

    return _submit_or_conflict(
        coordinator,
        review_id,
        "protocol",
        [],
        operations.operation("protocol.draft", review_id, request_payload, []),
        operation_kind="protocol.draft",
        request_payload=request_payload,
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
    operations: WorkflowOperationRegistry = Depends(get_workflow_operations),
    reviews: ReviewService = Depends(get_review_service),
) -> JobView:
    _require_review(review_id, reviews)
    try:
        inputs = coordinator.require_approved(
            review_id,
            ("question_pico", "records"),
        )
        PICODefinition.model_validate(inputs[0].payload.get("pico"))
        raw_papers = inputs[1].payload.get("papers")
        if not isinstance(raw_papers, list) or not raw_papers:
            raise WorkflowInputConflict("Approved Records contain no papers")
        for paper in raw_papers:
            Paper.model_validate(paper)
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved Screening inputs are invalid",
        ) from exc

    request_payload = request.model_dump(mode="json")

    return _submit_or_conflict(
        coordinator,
        review_id,
        "screening",
        inputs,
        operations.operation("screening.run", review_id, request_payload, inputs),
        operation_kind="screening.run",
        request_payload=request_payload,
    )


@router.post("/search/query", response_model=JobView, status_code=202)
def generate_search_query(
    review_id: str,
    request: SearchQueryWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    operations: WorkflowOperationRegistry = Depends(get_workflow_operations),
    reviews: ReviewService = Depends(get_review_service),
) -> JobView:
    _require_review(review_id, reviews)
    try:
        inputs = coordinator.require_approved(review_id, ("question_pico",))
        PICODefinition.model_validate(inputs[0].payload.get("pico"))
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved PICO artifact is invalid",
        ) from exc

    request_payload = request.model_dump(mode="json")

    return _submit_or_conflict(
        coordinator,
        review_id,
        "search",
        inputs,
        operations.operation("search.query", review_id, request_payload, inputs),
        operation_kind="search.query",
        request_payload=request_payload,
    )


@router.post("/search/run", response_model=JobView, status_code=202)
def run_search(
    review_id: str,
    request: SearchRunWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    operations: WorkflowOperationRegistry = Depends(get_workflow_operations),
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

    request_payload = request.model_dump(mode="json")

    return _submit_or_conflict(
        coordinator,
        review_id,
        "search",
        inputs,
        operations.operation("search.run", review_id, request_payload, inputs),
        operation_kind="search.run",
        request_payload=request_payload,
    )


@router.post("/extraction/run", response_model=JobView, status_code=202)
def run_extraction(
    review_id: str,
    request: ExtractionWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    operations: WorkflowOperationRegistry = Depends(get_workflow_operations),
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
        PICODefinition.model_validate(inputs[0].payload.get("pico"))
        for file_id in request.file_ids:
            record = storage.get(file_id)
            if record.review_id != review_id:
                raise WorkflowInputConflict("PDF does not belong to this Review")
            if record.mime_type != "application/pdf":
                raise WorkflowInputConflict("Extraction accepts PDF files only")
    except StoredFileNotFound as exc:
        raise HTTPException(status_code=409, detail=f"PDF not found: {exc}") from exc
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved Extraction inputs are invalid",
        ) from exc

    request_payload = request.model_dump(mode="json")

    return _submit_or_conflict(
        coordinator,
        review_id,
        "extraction",
        inputs,
        operations.operation("extraction.run", review_id, request_payload, inputs),
        operation_kind="extraction.run",
        request_payload=request_payload,
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
    operations: WorkflowOperationRegistry = Depends(get_workflow_operations),
    reviews: ReviewService = Depends(get_review_service),
    storage: FileStorage = Depends(get_file_storage),
) -> JobView:
    _require_review(review_id, reviews)
    try:
        inputs = coordinator.require_approved(review_id, ("question_pico",))
        PICODefinition.model_validate(inputs[0].payload.get("pico"))
        _review_datasets(review_id, request.file_ids, storage)
    except WorkflowInputConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved Meta-analysis inputs are invalid",
        ) from exc

    request_payload = request.model_dump(mode="json")

    return _submit_or_conflict(
        coordinator,
        review_id,
        "meta_analysis",
        inputs,
        operations.operation("meta.plan", review_id, request_payload, inputs),
        operation_kind="meta.plan",
        request_payload=request_payload,
    )


@router.post("/meta/run", response_model=JobView, status_code=202)
def run_meta_analysis(
    review_id: str,
    request: MetaRunWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    operations: WorkflowOperationRegistry = Depends(get_workflow_operations),
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

    request_payload = request.model_dump(mode="json")

    return _submit_or_conflict(
        coordinator,
        review_id,
        "meta_analysis",
        inputs,
        operations.operation("meta.run", review_id, request_payload, inputs),
        operation_kind="meta.run",
        request_payload=request_payload,
    )
