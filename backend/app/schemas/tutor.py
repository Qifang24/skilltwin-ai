from datetime import datetime
from pydantic import BaseModel, Field
from app.core.enums import EvidenceSufficiency
from app.schemas.common import SourceRef


class TutorChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    job_id: str
    task_id: str | None = None
    conversation_id: str | None = None


class TutorMessageRead(BaseModel):
    id: int
    role: str
    content: str
    sources: list[SourceRef] = Field(default_factory=list)
    created_at: datetime


class TutorChatResponse(BaseModel):
    conversation_id: str
    answer: TutorMessageRead
    reasoning_summary: str
    confidence: float
    evidence_sufficiency: EvidenceSufficiency
    warnings: list[str] = Field(default_factory=list)


class TutorConversationRead(BaseModel):
    id: str
    job_id: str
    task_id: str | None = None
    title: str | None = None
    updated_at: datetime
