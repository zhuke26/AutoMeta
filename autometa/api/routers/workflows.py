from fastapi import APIRouter, Depends, HTTPException

from autometa.agents.protocol_agent import ProtocolAgent
from autometa.api.dependencies import get_review_service, get_workflow_coordinator
from autometa.jobs.manager import JobConflict, JobContext
from autometa.schemas.jobs import JobView
from autometa.schemas.workflows import ProtocolWorkflowRequest
from autometa.services.reviews import ReviewNotFound, ReviewService
from autometa.services.workflows import WorkflowCoordinator


router = APIRouter(prefix="/reviews/{review_id}/workflow", tags=["workflow"])


@router.post("/protocol/draft", response_model=JobView, status_code=202)
def draft_protocol(
    review_id: str,
    request: ProtocolWorkflowRequest,
    coordinator: WorkflowCoordinator = Depends(get_workflow_coordinator),
    reviews: ReviewService = Depends(get_review_service),
) -> JobView:
    try:
        reviews.get(review_id)
    except ReviewNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Review not found: {review_id}",
        ) from exc

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

    try:
        return coordinator.submit(review_id, "protocol", [], operation)
    except JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
