"""真实用户测试记录与汇总报告接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.common import Page
from app.schemas.user_testing import (
    CompleteUserTestSessionRequest,
    CreateUserTestSessionRequest,
    UpdateUserTestTaskRequest,
    UserTestReportRead,
    UserTestScriptRead,
    UserTestSessionRead,
    UserTestTaskRead,
)
from app.services.user_testing_service import UserTestingService

router = APIRouter(prefix="/user-testing", tags=["user-testing"])


@router.get("/scripts", response_model=list[UserTestScriptRead])
def list_scripts(db: Session = Depends(get_db)) -> list[UserTestScriptRead]:
    return UserTestingService(db).scripts()


@router.post("/sessions", response_model=UserTestSessionRead, status_code=201)
def create_session(
    payload: CreateUserTestSessionRequest, db: Session = Depends(get_db)
) -> UserTestSessionRead:
    session = UserTestingService(db).create_session(payload)
    db.commit()
    return UserTestSessionRead.model_validate(UserTestingService(db).get_session(session.id))


@router.get("/sessions", response_model=Page[UserTestSessionRead])
def list_sessions(db: Session = Depends(get_db)) -> Page[UserTestSessionRead]:
    sessions = UserTestingService(db).list_sessions()
    return Page(
        items=[UserTestSessionRead.model_validate(session) for session in sessions],
        total=len(sessions),
        limit=len(sessions),
        offset=0,
    )


@router.get("/sessions/{session_id}", response_model=UserTestSessionRead)
def get_session(session_id: str, db: Session = Depends(get_db)) -> UserTestSessionRead:
    return UserTestSessionRead.model_validate(UserTestingService(db).get_session(session_id))


@router.patch("/tasks/{task_id}", response_model=UserTestTaskRead)
def update_task(
    task_id: str, payload: UpdateUserTestTaskRequest, db: Session = Depends(get_db)
) -> UserTestTaskRead:
    task = UserTestingService(db).update_task(task_id, payload)
    db.commit()
    return UserTestTaskRead.model_validate(task)


@router.post("/sessions/{session_id}/complete", response_model=UserTestSessionRead)
def complete_session(
    session_id: str,
    payload: CompleteUserTestSessionRequest,
    db: Session = Depends(get_db),
) -> UserTestSessionRead:
    session = UserTestingService(db).complete_session(session_id, payload)
    db.commit()
    return UserTestSessionRead.model_validate(session)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, db: Session = Depends(get_db)) -> Response:
    UserTestingService(db).delete_session(session_id)
    db.commit()
    return Response(status_code=204)


@router.get("/report", response_model=UserTestReportRead)
def report(db: Session = Depends(get_db)) -> UserTestReportRead:
    return UserTestingService(db).report()
