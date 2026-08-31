"""个性化学习路径接口（Module 4 下半）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import NotFoundError
from app.models.student import Student
from app.schemas.learning import (
    GenerateLearningPathRequest,
    GenerateLearningPathResponse,
    LearningPathRead,
    StartPathRetestRequest,
    StartPathRetestResponse,
    UpdateLearningPathItemRequest,
)
from app.services.learning_path_service import LearningPathService

router = APIRouter(tags=["learning-path"])


@router.post(
    "/students/{student_id}/learning-paths/generate",
    response_model=GenerateLearningPathResponse,
    status_code=201,
    summary="生成个性化学习路径",
    description=(
        "使用目标岗位的 approved 能力图谱与学生最新能力画像计算 Skill Gap。"
        "顺序由前置依赖和差距确定性计算，LLM 只撰写阶段说明。"
        "未测评技能不会被当作零分安排，而会提示先补测。"
    ),
)
def generate_learning_path(
    student_id: str,
    payload: GenerateLearningPathRequest,
    db: Session = Depends(get_db),
) -> GenerateLearningPathResponse:
    service = LearningPathService(db)
    generated = service.generate_for_student(
        student_id=student_id,
        job_id=payload.job_id,
        max_phases=payload.max_phases,
    )
    db.commit()
    path = service.latest_path(student_id, generated.path.job_id)
    if path is None:  # pragma: no cover - commit 后的防御性检查
        raise NotFoundError("学习路径生成后未能重新读取")
    return GenerateLearningPathResponse(
        path=LearningPathRead.model_validate(path),
        reasoning_summary=generated.reasoning_summary,
        sources=generated.sources,
        confidence=generated.confidence,
        evidence_sufficiency=generated.evidence_sufficiency,
        ai_generated=generated.ai_generated,
        warnings=generated.warnings,
    )


@router.get(
    "/students/{student_id}/learning-paths/latest",
    response_model=LearningPathRead,
    summary="查询最新学习路径",
)
def get_latest_learning_path(
    student_id: str,
    job_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> LearningPathRead:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError(
            f"未找到学生：{student_id}", detail={"student_id": student_id}
        )
    path = LearningPathService(db).latest_path(student_id, job_id)
    if path is None:
        raise NotFoundError(
            "该学生尚无学习路径",
            detail={"student_id": student_id, "job_id": job_id},
        )
    return LearningPathRead.model_validate(path)


@router.patch(
    "/students/{student_id}/learning-path-items/{item_id}",
    response_model=LearningPathRead,
    summary="更新学习项状态并重算路径进度",
    description=(
        "知识、行动建议和实训任务可由学生标记完成或重新打开。"
        "该操作只记录学习进度，不会直接提高能力分；阶段复测必须判分后由系统完成。"
    ),
)
def update_learning_path_item(
    student_id: str,
    item_id: str,
    payload: UpdateLearningPathItemRequest,
    db: Session = Depends(get_db),
) -> LearningPathRead:
    path = LearningPathService(db).update_item_status(
        student_id=student_id,
        item_id=item_id,
        status=payload.status,
        note=payload.note,
    )
    db.commit()
    return LearningPathRead.model_validate(path)


@router.post(
    "/students/{student_id}/learning-path-items/{item_id}/retest",
    response_model=StartPathRetestResponse,
    status_code=201,
    summary="从学习路径发起关联复测",
    description=(
        "复测与具体学习项建立可审计关联。交卷判分后会完成该学习项、归档旧路径，"
        "并依据最新能力画像自动重算路径。"
    ),
)
def start_learning_path_retest(
    student_id: str,
    item_id: str,
    payload: StartPathRetestRequest,
    db: Session = Depends(get_db),
) -> StartPathRetestResponse:
    started = LearningPathService(db).start_retest(
        student_id=student_id,
        item_id=item_id,
        item_count=payload.item_count,
    )
    db.commit()
    return StartPathRetestResponse(
        assessment_id=started.assessment.id,
        student_id=started.assessment.student_id,
        job_id=started.assessment.job_id,
        notes=started.notes,
    )
