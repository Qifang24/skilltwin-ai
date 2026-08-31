from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.schemas.tutor import TutorChatRequest, TutorChatResponse
from app.services.tutor_service import TutorService
router = APIRouter(prefix="/students/{student_id}/tutor", tags=["tutor"])
@router.post("/chat", response_model=TutorChatResponse)
def tutor_chat(student_id: str, payload: TutorChatRequest, db: Session = Depends(get_db)) -> TutorChatResponse:
    return TutorService(db).chat(student_id, job_id=payload.job_id, message=payload.message, task_id=payload.task_id, conversation_id=payload.conversation_id)
