"""学生、测评与能力画像接口（Module 4）。

合规：只存化名；`DELETE /students/{id}` 会级联删除全部关联数据。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.enums import GraphStatus
from app.core.errors import NotFoundError, ValidationError
from app.models.competency import CompetencyGraph
from app.models.ontology import Job, Skill
from app.models.student import Assessment, AssessmentItem, SkillProfile, Student
from app.schemas.assessment import (
    AssessmentRead,
    CreateStudentRequest,
    GapRead,
    ItemRead,
    ProfileEntryRead,
    SkillGapReport,
    SkillProfileRead,
    StartAssessmentRequest,
    StudentRead,
    SubmitAssessmentRequest,
    SubmitResult,
)
from app.schemas.learning import LearningPathAdaptationRead
from app.services.assessment_service import AssessmentService
from app.services.competency_graph_service import CompetencyGraphService
from app.services.learning_path_service import LearningPathService
from app.services.scoring import SkillEstimate, compute_gaps

router = APIRouter(tags=["student"])


def _skill_meta(db: Session, code: str) -> tuple[str | None, str | None]:
    skill = db.get(Skill, code)
    return (skill.name_zh, skill.category.value) if skill else (None, None)


def _profile_read(db: Session, profile: SkillProfile, notes: list[str]) -> SkillProfileRead:
    item = SkillProfileRead.model_validate(profile)
    entries = []
    for entry in sorted(profile.entries, key=lambda e: -e.score):
        read = ProfileEntryRead.model_validate(entry)
        read.skill_name, read.category = _skill_meta(db, entry.skill_code)
        read.reliable = entry.is_reliable
        entries.append(read)
    item.entries = entries
    item.notes = notes
    return item


# ---------------------------------------------------------------- 学生
@router.post(
    "/students",
    response_model=StudentRead,
    status_code=201,
    summary="创建学生（化名）",
    description="**只存化名**，系统不存储姓名、学号等真实个人信息。",
)
def create_student(
    payload: CreateStudentRequest, db: Session = Depends(get_db)
) -> StudentRead:
    if payload.target_job_id and db.get(Job, payload.target_job_id) is None:
        raise NotFoundError(f"未找到岗位：{payload.target_job_id}")

    student = Student(
        id=f"stu_{uuid.uuid4().hex[:12]}",
        display_name=payload.display_name,
        target_job_id=payload.target_job_id,
        cohort=payload.cohort,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return StudentRead.model_validate(student)


@router.get("/students", response_model=list[StudentRead], summary="学生列表")
def list_students(db: Session = Depends(get_db)) -> list[StudentRead]:
    students = db.execute(select(Student).order_by(Student.created_at)).scalars().all()
    return [StudentRead.model_validate(s) for s in students]


@router.get("/students/{student_id}", response_model=StudentRead, summary="学生详情")
def get_student(student_id: str, db: Session = Depends(get_db)) -> StudentRead:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError(f"未找到学生：{student_id}")
    return StudentRead.model_validate(student)


@router.delete(
    "/students/{student_id}",
    summary="删除学生及其全部数据",
    description="合规要求：测评记录、作答、能力画像一并彻底删除。",
)
def delete_student(student_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError(f"未找到学生：{student_id}")
    db.delete(student)
    db.commit()
    return {"deleted": student_id}


# ---------------------------------------------------------------- 测评
@router.post(
    "/students/{student_id}/assessments",
    response_model=AssessmentRead,
    status_code=201,
    summary="开始诊断测评",
)
def start_assessment(
    student_id: str,
    payload: StartAssessmentRequest,
    db: Session = Depends(get_db),
) -> AssessmentRead:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError(f"未找到学生：{student_id}")

    service = AssessmentService(db)
    started = service.start(
        student=student,
        job_id=payload.job_id,
        item_count=payload.item_count,
        assessment_type=payload.type,
    )
    db.commit()
    db.refresh(started.assessment)
    return _assessment_read(db, started.assessment, started.notes)


def _assessment_read(
    db: Session, assessment: Assessment, notes: list[str] | None = None
) -> AssessmentRead:
    read = AssessmentRead.model_validate(assessment)
    read.notes = notes or []
    items = []
    for record in assessment.responses:
        item = db.get(AssessmentItem, record.item_id)
        if item is None:
            continue
        entry = ItemRead.model_validate(item)
        entry.skill_codes = [link.skill_code for link in item.skills]
        items.append(entry)
    read.items = items
    return read


@router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentRead,
    summary="取试卷",
    description="**不含答案** —— 答案仅在交卷后返回。",
)
def get_assessment(assessment_id: str, db: Session = Depends(get_db)) -> AssessmentRead:
    assessment = db.execute(
        select(Assessment)
        .options(selectinload(Assessment.responses))
        .where(Assessment.id == assessment_id)
    ).scalar_one_or_none()
    if assessment is None:
        raise NotFoundError(f"未找到测评：{assessment_id}")
    return _assessment_read(db, assessment)


@router.post(
    "/assessments/{assessment_id}/submit",
    response_model=SubmitResult,
    summary="交卷并生成能力画像",
    description=(
        "判分与能力估计均为确定性计算，不经模型。"
        "能力值带 95% 置信区间与证据条数 —— 少量题目算不出精确值。"
    ),
)
def submit_assessment(
    assessment_id: str,
    payload: SubmitAssessmentRequest,
    db: Session = Depends(get_db),
) -> SubmitResult:
    service = AssessmentService(db)
    answers = {r.item_id: r.response for r in payload.responses}
    result = service.submit(assessment_id, answers)
    adaptation = LearningPathService(db).adapt_after_scored_assessment(assessment_id)
    db.commit()
    db.refresh(result.profile)

    path_update = (
        LearningPathAdaptationRead(
            linked_item_id=adaptation.linked_item_id,
            archived_path_id=adaptation.archived_path_id,
            new_path_id=adaptation.new_path_id,
            recalculated=adaptation.recalculated,
            message=adaptation.message,
            warnings=adaptation.warnings or [],
        )
        if adaptation
        else None
    )

    return SubmitResult(
        assessment_id=assessment_id,
        profile_id=result.profile.id,
        correct_count=result.correct_count,
        total_count=result.total_count,
        updated_skill_codes=result.updated_skill_codes,
        inherited_skill_codes=result.inherited_skill_codes,
        learning_path_update=path_update,
        profile=_profile_read(db, result.profile, result.notes),
    )


# ---------------------------------------------------------------- 画像
@router.get(
    "/students/{student_id}/skill-profile",
    response_model=SkillProfileRead,
    summary="最新能力画像",
)
def get_profile(
    student_id: str,
    job_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SkillProfileRead:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError(f"未找到学生：{student_id}")

    target_job = job_id or student.target_job_id
    profile = AssessmentService(db).latest_profile(student_id, target_job)
    if profile is None:
        raise NotFoundError(
            "该学生尚无能力画像，请先完成一次诊断测评",
            detail={"student_id": student_id},
        )
    return _profile_read(db, profile, [])


@router.get(
    "/students/{student_id}/skill-gap",
    response_model=SkillGapReport,
    summary="能力差距分析",
    description=(
        "当前能力画像 vs 已审核图谱的目标能力向量。"
        "未测评的技能会标记 untested —— 学习路径不应把「没测过」当成「很差」。"
    ),
)
def get_gap(
    student_id: str,
    job_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SkillGapReport:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError(f"未找到学生：{student_id}")

    target_job = job_id or student.target_job_id
    if not target_job:
        raise ValidationError("请指定目标岗位，或先为该学生设置 target_job_id")

    graph = db.execute(
        select(CompetencyGraph)
        .options(selectinload(CompetencyGraph.nodes))
        .where(
            CompetencyGraph.job_id == target_job,
            CompetencyGraph.status == GraphStatus.APPROVED,
        )
    ).scalars().first()
    if graph is None:
        raise ValidationError(
            f"岗位 {target_job} 尚无已审核的能力图谱，无法确定目标能力基线。"
            f"请教师先审核通过一份图谱。",
            detail={"job_id": target_job},
        )

    target_vector = CompetencyGraphService(db).target_skill_vector(graph)
    profile = AssessmentService(db).latest_profile(student_id, target_job)

    estimates: dict[str, SkillEstimate] = {}
    if profile:
        for entry in profile.entries:
            estimates[entry.skill_code] = SkillEstimate(
                skill_code=entry.skill_code,
                score=entry.score,
                score_low=entry.score_low,
                score_high=entry.score_high,
                confidence=entry.confidence,
                evidence_count=entry.evidence_count,
                method=entry.method,
            )

    gaps = []
    for gap in compute_gaps(target_vector, estimates):
        read = GapRead(**gap.__dict__, untested=gap.evidence_count == 0)
        read.skill_name, read.category = _skill_meta(db, gap.skill_code)
        gaps.append(read)

    notes: list[str] = []
    if profile is None:
        notes.append("该学生尚未完成测评，以下差距均按「未测评」处理，仅供参考")
    untested = [g for g in gaps if g.untested]
    if untested:
        notes.append(
            f"{len(untested)}/{len(gaps)} 项技能尚未被题目考查，"
            f"其差距值不代表真实水平，建议补充题库后复测"
        )

    return SkillGapReport(
        student_id=student_id,
        job_id=target_job,
        graph_id=graph.id,
        profile_id=profile.id if profile else None,
        gaps=gaps,
        notes=notes,
    )
