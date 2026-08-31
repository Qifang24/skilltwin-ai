"""实训任务接口（Module 3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.agents.training_task import TaskGenerationInput, TrainingTaskAgent
from app.core.db import get_db
from app.core.enums import TaskDifficulty, TaskStatus
from app.core.errors import NotFoundError
from app.models.competency import CompetencyNode
from app.models.ontology import Job, Skill
from app.models.training import TrainingTask
from app.schemas.common import Page
from app.schemas.training import (
    GenerateTaskRequest,
    PublishTaskRequest,
    TaskSkillRead,
    TrainingTaskDetail,
    TrainingTaskSummary,
)
from app.services.training_task_service import TrainingTaskService

router = APIRouter(prefix="/training-tasks", tags=["training-task"])


def _summarise(task: TrainingTask) -> TrainingTaskSummary:
    item = TrainingTaskSummary.model_validate(task)
    item.skill_count = len(task.skills)
    return item


def _detail(task: TrainingTask, db: Session) -> TrainingTaskDetail:
    item = TrainingTaskDetail(**_summarise(task).model_dump(), scenario=task.scenario)
    item.objectives = list(task.objectives)
    item.steps = list(task.steps)
    item.deliverables = list(task.deliverables)
    item.rubric = list(task.rubric)
    item.common_mistakes = list(task.common_mistakes)
    item.extensions = list(task.extensions)
    item.safety_notes = task.safety_notes
    item.citations = list(task.citations)
    item.generation_run_id = task.generation_run_id

    skills = []
    for link in task.skills:
        entry = TaskSkillRead.model_validate(link)
        skill = db.get(Skill, link.skill_code)
        entry.skill_name = skill.name_zh if skill else None
        skills.append(entry)
    item.skills = skills

    if task.source_node_id:
        node = db.get(CompetencyNode, task.source_node_id)
        item.source_node_name = node.name if node else None
    return item


@router.post(
    "/generate",
    response_model=TrainingTaskDetail,
    summary="从能力节点生成实训任务",
    description=(
        "输入能力图谱中的节点（通常是能力单元），生成结构化实训任务。"
        "只能从**已审核通过**的图谱派生——草案图谱的节点编码仍可能变动。"
    ),
)
def generate_task(
    payload: GenerateTaskRequest, db: Session = Depends(get_db)
) -> TrainingTaskDetail:
    service = TrainingTaskService(db)
    node, path, skills = service.node_context(payload.node_id)

    job = db.get(Job, node.graph.job_id)
    agent = TrainingTaskAgent()
    envelope = agent.run(
        db,
        TaskGenerationInput(
            job_name=job.name if job else node.graph.job_id,
            unit_name=node.name,
            unit_description=node.description,
            path=path,
            skills=skills,
            difficulty=payload.difficulty,
            context=payload.context,
        ),
    )

    result = service.persist(
        node=node,
        draft=envelope.result,
        sources=envelope.sources,
        generation_run_id=envelope.llm_run_id,
    )
    db.commit()
    db.refresh(result.task)

    detail = _detail(result.task, db)
    detail.warnings = [*envelope.warnings, *result.warnings]
    return detail


@router.get("", response_model=Page[TrainingTaskSummary], summary="实训任务列表")
def list_tasks(
    db: Session = Depends(get_db),
    job_id: str | None = Query(default=None),
    status: TaskStatus | None = Query(default=None),
    difficulty: TaskDifficulty | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[TrainingTaskSummary]:
    filters = []
    if job_id:
        filters.append(TrainingTask.job_id == job_id)
    if status:
        filters.append(TrainingTask.status == status)
    if difficulty:
        filters.append(TrainingTask.difficulty == difficulty)

    total = db.execute(
        select(func.count()).select_from(TrainingTask).where(*filters)
    ).scalar_one()
    tasks = (
        db.execute(
            select(TrainingTask)
            .options(selectinload(TrainingTask.skills))
            .where(*filters)
            .order_by(TrainingTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return Page[TrainingTaskSummary](
        items=[_summarise(t) for t in tasks], total=total, limit=limit, offset=offset
    )


@router.get("/{task_id}", response_model=TrainingTaskDetail, summary="任务详情")
def get_task(task_id: str, db: Session = Depends(get_db)) -> TrainingTaskDetail:
    task = db.execute(
        select(TrainingTask)
        .options(selectinload(TrainingTask.skills))
        .where(TrainingTask.id == task_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError(f"未找到任务：{task_id}", detail={"task_id": task_id})
    return _detail(task, db)


@router.post(
    "/{task_id}/publish",
    response_model=TrainingTaskSummary,
    summary="发布任务",
    description="教师确认后发布给学生。未关联规范技能的任务不允许发布。",
)
def publish_task(
    task_id: str, payload: PublishTaskRequest, db: Session = Depends(get_db)
) -> TrainingTaskSummary:
    task = TrainingTaskService(db).publish(task_id, payload.published_by)
    db.commit()
    db.refresh(task)
    return _summarise(task)
