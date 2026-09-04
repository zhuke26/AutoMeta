from pydantic import BaseModel, Field


class ProtocolWorkflowRequest(BaseModel):
    research_question: str = Field(min_length=10, max_length=4000)
