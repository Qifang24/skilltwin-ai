"""实训任务接口（Module 3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.agents.training_task import TaskGenerationInput, TrainingTaskAgent
from app.core.db import get_db
from app.core.enums import TaskDifficulty, TaskStatus
from app.core.errors import ConflictError, NotFoundError
from app.models.competency import CompetencyNode
from app.models.curriculum import CourseSkillCoverage, CurriculumCourse, CurriculumPlan
from app.models.ontology import Job, Skill
from app.models.training import TrainingTask
from app.rag.retriever import HybridRetriever
from app.schemas.common import Page
from app.schemas.training import (
    GenerateTaskRequest,
    PublishTaskRequest,
    TaskCourseEvidenceRead,
    TaskCurriculumCourseRead,
    TaskCurriculumPlanRead,
    TaskSkillRead,
    TrainingTaskDetail,
    TrainingTaskSummary,
    UpdateTrainingTaskRequest,
)
from app.models.training import TrainingTaskSkill
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

    if task.plan_id:
        plan = db.get(CurriculumPlan, task.plan_id)
        if plan:
            item.curriculum_plan = TaskCurriculumPlanRead(
                id=plan.id,
                name=plan.name,
                profession=plan.profession,
                version=plan.version,
                source_name=plan.source_name,
                source_url=plan.source_url,
                is_partial=plan.is_partial,
            )
    if task.course_id:
        course = db.get(CurriculumCourse, task.course_id)
        if course:
            item.curriculum_course = TaskCurriculumCourseRead(
                id=course.id,
                plan_id=course.plan_id,
                course_code=course.course_code,
                name=course.name,
                category=course.category,
                total_hours=course.total_hours,
                objectives=course.objectives,
                description=course.description,
                teaching_content=course.teaching_content,
                knowledge_points=course.knowledge_points,
                practical_content=course.practical_content,
                learning_outcomes=course.learning_outcomes,
            )
            # 新任务在生成时已把课程依据固化到 citations；优先返回快照，
            # 这样教师日后修改课程或技能映射不会改变“当时为何这样生成”。
            evidence = [
                TaskCourseEvidenceRead(
                    evidence_type=str(raw["evidence_type"]),
                    field=raw.get("field"),
                    skill_code=raw.get("skill_code"),
                    chunk_id=raw.get("chunk_id"),
                    page=raw.get("page"),
                    quote=str(raw["quote"]),
                    is_generation_snapshot=True,
                )
                for raw in (task.citations or [])
                if raw.get("is_generation_snapshot")
                and raw.get("course_id") == course.id
                and raw.get("evidence_type")
                and raw.get("quote")
            ]
            if not evidence:
                # 兼容已经带 course_id、但创建于证据快照上线前的历史任务。
                if course.source_quote:
                    evidence.append(
                        TaskCourseEvidenceRead(
                            evidence_type="course_source",
                            field="source_quote",
                            chunk_id=course.source_chunk_id,
                            page=course.source_page,
                            quote=course.source_quote,
                        )
                    )
                for field, raw in (course.field_evidence or {}).items():
                    if isinstance(raw, dict) and raw.get("quote"):
                        evidence.append(
                            TaskCourseEvidenceRead(
                                evidence_type="course_field",
                                field=field,
                                chunk_id=raw.get("chunk_id") or course.source_chunk_id,
                                page=raw.get("page") or course.source_page,
                                quote=str(raw["quote"]),
                            )
                        )
                skill_codes = {link.skill_code for link in task.skills}
                if skill_codes:
                    mappings = db.execute(
                        select(CourseSkillCoverage)
                        .where(
                            CourseSkillCoverage.course_id == course.id,
                            CourseSkillCoverage.skill_code.in_(skill_codes),
                            CourseSkillCoverage.coverage_status.in_(("covered", "partial")),
                        )
                        .order_by(CourseSkillCoverage.skill_code)
                    ).scalars()
                    evidence.extend(
                        TaskCourseEvidenceRead(
                            evidence_type="skill_coverage",
                            skill_code=mapping.skill_code,
                            chunk_id=mapping.source_chunk_id,
                            page=mapping.source_page,
                            quote=mapping.evidence_quote,
                        )
                        for mapping in mappings
                        if mapping.evidence_quote
                    )
            item.course_evidence = evidence
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
    curriculum = service.curriculum_context(
        node, plan_id=payload.plan_id, course_id=payload.course_id
    )

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
            curriculum_context=curriculum.prompt_text() if curriculum else None,
        ),
    )

    result = service.persist(
        node=node,
        draft=envelope.result,
        sources=envelope.sources,
        generation_run_id=envelope.llm_run_id,
        curriculum=curriculum,
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
    plan_id: str | None = Query(default=None),
    course_id: str | None = Query(default=None),
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
    if plan_id:
        filters.append(TrainingTask.plan_id == plan_id)
    if course_id:
        filters.append(TrainingTask.course_id == course_id)

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


@router.patch(
    "/{task_id}",
    response_model=TrainingTaskDetail,
    summary="教师修改实训任务",
)
def update_task(
    task_id: str, payload: UpdateTrainingTaskRequest, db: Session = Depends(get_db)
) -> TrainingTaskDetail:
    task = db.execute(
        select(TrainingTask)
        .options(selectinload(TrainingTask.skills))
        .where(TrainingTask.id == task_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError(f"未找到任务：{task_id}", detail={"task_id": task_id})

    unknown_codes = [
        item.skill_code for item in payload.skills if db.get(Skill, item.skill_code) is None
    ]
    if unknown_codes:
        raise ConflictError(f"存在未收录的技能编码：{', '.join(sorted(set(unknown_codes)))}")
    if sum(item.weight for item in payload.skills) <= 0:
        raise ConflictError("训练技能权重总和必须大于 0")

    task.title = payload.title
    task.scenario = payload.scenario
    task.difficulty = payload.difficulty
    task.est_minutes = payload.est_minutes
    task.objectives = [item.model_dump() for item in payload.objectives]
    task.steps = [item.model_dump() for item in sorted(payload.steps, key=lambda item: item.order)]
    task.deliverables = list(payload.deliverables)
    task.rubric = [item.model_dump() for item in payload.rubric]
    task.common_mistakes = [item.model_dump() for item in payload.common_mistakes]
    task.extensions = list(payload.extensions)
    task.safety_notes = payload.safety_notes
    task.edited_by_human = True
    db.execute(delete(TrainingTaskSkill).where(TrainingTaskSkill.task_id == task_id))
    for item in payload.skills:
        db.add(TrainingTaskSkill(
            task_id=task_id,
            skill_code=item.skill_code,
            weight=item.weight,
            target_level=item.target_level,
        ))
    db.commit()
    task = db.execute(
        select(TrainingTask)
        .options(selectinload(TrainingTask.skills))
        .where(TrainingTask.id == task_id)
    ).scalar_one()
    return _detail(task, db)


@router.post(
    "/{task_id}/refresh-citations",
    response_model=TrainingTaskDetail,
    summary="重新检索知识库依据",
)
def refresh_task_citations(
    task_id: str, db: Session = Depends(get_db)
) -> TrainingTaskDetail:
    task = db.execute(
        select(TrainingTask)
        .options(selectinload(TrainingTask.skills))
        .where(TrainingTask.id == task_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError(f"未找到任务：{task_id}", detail={"task_id": task_id})
    if task.status is not TaskStatus.DRAFT:
        raise ConflictError("已发布任务不能更新设计依据；请创建新草稿后再检索。")

    source_node = db.get(CompetencyNode, task.source_node_id) if task.source_node_id else None
    skill_names = [
        skill.name_zh
        for link in task.skills
        if (skill := db.get(Skill, link.skill_code)) is not None
    ]
    query = " ".join(
        part
        for part in (task.title, source_node.name if source_node else None, *skill_names, "实训 操作规范 教学要求")
        if part
    )
    chunks = HybridRetriever().search(db, query, top_n=6)
    curriculum_snapshots = [
        raw for raw in (task.citations or []) if raw.get("is_generation_snapshot")
    ]
    task.citations = [
        {
            "chunk_id": chunk.chunk_id,
            "source_name": chunk.source_name,
            "page": chunk.page,
            "section": chunk.section,
            "quote": chunk.text[:300],
        }
        for chunk in chunks
    ] + curriculum_snapshots
    db.commit()
    db.refresh(task)
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
