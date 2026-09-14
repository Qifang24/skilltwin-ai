"""课程导入、结构性覆盖、人工校正与优化闭环。"""

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ConflictError, NotFoundError
from app.models.curriculum import CourseSkillCoverage, CurriculumAnalysis, CurriculumCourse, CurriculumPlan, OptimizationRun, OptimizationSuggestion, SkillCoverage
from app.models.training import TrainingTask
from app.schemas.curriculum import (
    CourseSkillMappingRead, CourseSkillMappingWrite, CurriculumAnalysisCreate,
    CurriculumCourseRead, CurriculumCourseWrite, CurriculumGapDashboardRead,
    CurriculumImportBatchRead, CurriculumImportConfirmRequest, CurriculumOptimizationRead,
    CurriculumPlanRead, CurriculumPlanWrite, SuggestionAliasPatch, SuggestionPatch,
)
from app.services.curriculum_gap_service import CurriculumGapService
from app.services.curriculum_management_service import CurriculumManagementService
from app.services.curriculum_optimization_service import CurriculumOptimizationService

router = APIRouter(prefix="/curriculum", tags=["curriculum"])
import_router = APIRouter(prefix="/curriculum-imports", tags=["curriculum-imports"])


@router.get("/{job_id}/gap", response_model=CurriculumGapDashboardRead)
def get_curriculum_gap(job_id: str, plan_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> CurriculumGapDashboardRead:
    return CurriculumGapService(db).dashboard(job_id, plan_id)


@router.get("/{job_id}/optimization", response_model=CurriculumOptimizationRead)
def get_curriculum_optimization(job_id: str, plan_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> CurriculumOptimizationRead:
    return CurriculumOptimizationService(db).generate(job_id, plan_id)


def _import_payload(service: CurriculumManagementService, batch) -> dict:
    return {
        "id": batch.id, "filename": batch.filename, "status": batch.status,
        "source_name": batch.source_name, "source_url": batch.source_url,
        "license_note": batch.license_note, "error_message": batch.error_message,
        "confirmed_plan_id": batch.confirmed_plan_id,
        "courses": [{"id": row.id, "row_number": row.row_number, "status": row.status, "data": row.structured_data, "field_evidence": row.field_evidence, "errors": row.errors} for row in service.drafts(batch.id)],
    }


@import_router.post("", response_model=CurriculumImportBatchRead, status_code=201, operation_id="create_curriculum_import_alias")
@router.post("/imports", response_model=CurriculumImportBatchRead, status_code=201, operation_id="create_curriculum_import")
async def create_curriculum_import(
    file: UploadFile = File(...), source_name: str = Form(...),
    source_url: str | None = Form(None), license_note: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    service = CurriculumManagementService(db)
    batch = service.create_import(filename=file.filename or "curriculum.txt", content=await file.read(), source_name=source_name, source_url=source_url, license_note=license_note)
    db.commit()
    return _import_payload(service, batch)


@import_router.get("/{batch_id}", response_model=CurriculumImportBatchRead, operation_id="get_curriculum_import_alias")
@router.get("/imports/{batch_id}", response_model=CurriculumImportBatchRead, operation_id="get_curriculum_import")
def get_curriculum_import(batch_id: str, db: Session = Depends(get_db)) -> dict:
    service = CurriculumManagementService(db)
    return _import_payload(service, service.get_import(batch_id))


@import_router.get("/{batch_id}/preview", response_model=CurriculumImportBatchRead, operation_id="preview_curriculum_import_alias")
@router.get("/imports/{batch_id}/preview", response_model=CurriculumImportBatchRead, operation_id="preview_curriculum_import")
def preview_curriculum_import(batch_id: str, db: Session = Depends(get_db)) -> dict:
    service = CurriculumManagementService(db)
    return _import_payload(service, service.get_import(batch_id))


@import_router.post("/{batch_id}/retry", response_model=CurriculumImportBatchRead, operation_id="retry_curriculum_import_alias")
@router.post("/imports/{batch_id}/retry", response_model=CurriculumImportBatchRead, operation_id="retry_curriculum_import")
def retry_curriculum_import(batch_id: str, db: Session = Depends(get_db)) -> dict:
    service = CurriculumManagementService(db)
    batch = service.get_import(batch_id)
    try:
        service.parse_import(batch)
    finally:
        db.commit()
    return _import_payload(service, batch)


@import_router.post("/{batch_id}/confirm", response_model=CurriculumPlanRead, operation_id="confirm_curriculum_import_alias")
@router.post("/imports/{batch_id}/confirm", response_model=CurriculumPlanRead, operation_id="confirm_curriculum_import")
def confirm_curriculum_import(batch_id: str, payload: CurriculumImportConfirmRequest, db: Session = Depends(get_db)) -> CurriculumPlan:
    service = CurriculumManagementService(db)
    try:
        plan = service.confirm_import(batch_id, **payload.model_dump())
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("课程资料中存在重复课程名称，请先点击“重新解析”后再确认。") from exc
    except Exception:
        db.rollback(); raise
    return plan


@router.get("/plans", response_model=list[CurriculumPlanRead])
def list_curriculum_plans(db: Session = Depends(get_db)) -> list[dict]:
    rows = list(db.execute(select(CurriculumPlan).order_by(CurriculumPlan.updated_at.desc())).scalars())
    counts = dict(db.execute(select(CurriculumCourse.plan_id, func.count()).group_by(CurriculumCourse.plan_id)).all())
    return [{"id": p.id, "name": p.name, "profession": p.profession, "version": p.version, "source_name": p.source_name, "source_url": p.source_url, "license_note": p.license_note, "is_partial": p.is_partial, "is_active": p.is_active, "course_count": counts.get(p.id, 0)} for p in rows]


@router.post("/plans", response_model=CurriculumPlanRead, status_code=201)
def create_curriculum_plan(payload: CurriculumPlanWrite, db: Session = Depends(get_db)) -> dict:
    if db.get(CurriculumPlan, payload.id):
        from app.core.errors import ConflictError
        raise ConflictError(f"培养方案 ID 已存在：{payload.id}")
    plan = CurriculumPlan(**payload.model_dump()); db.add(plan); db.commit()
    return {**payload.model_dump(), "course_count": 0}


@router.get("/plans/{plan_id}", response_model=CurriculumPlanRead)
def get_curriculum_plan(plan_id: str, db: Session = Depends(get_db)) -> dict:
    plan = db.get(CurriculumPlan, plan_id)
    if not plan: raise NotFoundError(f"未找到培养方案：{plan_id}")
    count = db.execute(select(func.count()).select_from(CurriculumCourse).where(CurriculumCourse.plan_id == plan_id)).scalar_one()
    return {"id": plan.id, "name": plan.name, "profession": plan.profession, "version": plan.version, "source_name": plan.source_name, "source_url": plan.source_url, "license_note": plan.license_note, "is_partial": plan.is_partial, "is_active": plan.is_active, "course_count": count}


@router.delete("/plans/{plan_id}", status_code=204)
def delete_curriculum_plan(plan_id: str, db: Session = Depends(get_db)) -> Response:
    plan = db.get(CurriculumPlan, plan_id)
    if not plan:
        raise NotFoundError(f"未找到培养方案：{plan_id}")
    linked_tasks = db.execute(
        select(func.count()).select_from(TrainingTask).where(TrainingTask.plan_id == plan_id)
    ).scalar_one()
    if linked_tasks:
        raise ConflictError(
            f"该培养方案已关联 {linked_tasks} 个实训任务，不能删除；"
            "请保留方案作为任务生成依据。"
        )
    db.delete(plan)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("该培养方案仍被其他数据引用，暂时不能删除。") from exc
    return Response(status_code=204)


@router.patch("/plans/{plan_id}", response_model=CurriculumPlanRead)
def update_curriculum_plan(plan_id: str, payload: CurriculumPlanWrite, db: Session = Depends(get_db)) -> dict:
    plan = db.get(CurriculumPlan, plan_id)
    if not plan: raise NotFoundError(f"未找到培养方案：{plan_id}")
    for key, value in payload.model_dump(exclude={"id"}).items(): setattr(plan, key, value)
    db.commit(); return get_curriculum_plan(plan_id, db)


@router.get("/plans/{plan_id}/courses", response_model=list[CurriculumCourseRead])
def list_curriculum_courses(plan_id: str, db: Session = Depends(get_db)) -> list[CurriculumCourse]:
    return list(db.execute(select(CurriculumCourse).where(CurriculumCourse.plan_id == plan_id).order_by(CurriculumCourse.name)).scalars())


@router.post("/plans/{plan_id}/courses", response_model=CurriculumCourseRead, status_code=201)
def create_curriculum_course(plan_id: str, payload: CurriculumCourseWrite, db: Session = Depends(get_db)) -> CurriculumCourse:
    course = CurriculumManagementService(db).add_course(plan_id, payload.model_dump(exclude_none=True)); db.commit(); return course


@router.get("/courses/{course_id}", response_model=CurriculumCourseRead)
def get_curriculum_course(course_id: str, db: Session = Depends(get_db)) -> CurriculumCourse:
    course = db.get(CurriculumCourse, course_id)
    if not course: raise NotFoundError(f"未找到课程：{course_id}")
    return course


@router.patch("/courses/{course_id}", response_model=CurriculumCourseRead)
def update_curriculum_course(course_id: str, payload: CurriculumCourseWrite, db: Session = Depends(get_db)) -> CurriculumCourse:
    course = db.get(CurriculumCourse, course_id)
    if not course: raise NotFoundError(f"未找到课程：{course_id}")
    for key, value in payload.model_dump(exclude={"id"}).items(): setattr(course, key, value)
    CurriculumManagementService(db).refresh_plan_analyses(course.plan_id); db.commit(); return course


@router.delete("/courses/{course_id}", status_code=204)
def delete_curriculum_course(course_id: str, db: Session = Depends(get_db)) -> Response:
    course = db.get(CurriculumCourse, course_id)
    if not course: raise NotFoundError(f"未找到课程：{course_id}")
    linked_tasks = db.execute(
        select(func.count()).select_from(TrainingTask).where(TrainingTask.course_id == course_id)
    ).scalar_one()
    if linked_tasks:
        raise ConflictError(
            f"该课程已关联 {linked_tasks} 个实训任务，不能删除；"
            "请保留课程作为任务生成依据。"
        )
    plan_id = course.plan_id; db.delete(course); db.flush(); CurriculumManagementService(db).refresh_plan_analyses(plan_id); db.commit()
    return Response(status_code=204)


@router.get("/courses/{course_id}/skills", response_model=list[CourseSkillMappingRead])
def list_course_skill_mappings(course_id: str, db: Session = Depends(get_db)) -> list[CourseSkillCoverage]:
    if not db.get(CurriculumCourse, course_id): raise NotFoundError(f"未找到课程：{course_id}")
    return list(db.execute(select(CourseSkillCoverage).where(CourseSkillCoverage.course_id == course_id).order_by(CourseSkillCoverage.skill_code)).scalars())


@router.post("/courses/{course_id}/skills", response_model=CourseSkillMappingRead, status_code=201)
def create_course_skill_mapping(course_id: str, payload: CourseSkillMappingWrite, db: Session = Depends(get_db)) -> CourseSkillCoverage:
    item = CurriculumManagementService(db).upsert_mapping(course_id, payload.model_dump()); db.commit(); return item


@router.patch("/courses/{course_id}/skills/{mapping_id}", response_model=CourseSkillMappingRead)
def update_course_skill_mapping(course_id: str, mapping_id: int, payload: CourseSkillMappingWrite, db: Session = Depends(get_db)) -> CourseSkillCoverage:
    item = CurriculumManagementService(db).upsert_mapping(course_id, payload.model_dump(), mapping_id); db.commit(); return item


@router.delete("/courses/{course_id}/skills/{mapping_id}", status_code=204)
def delete_course_skill_mapping(course_id: str, mapping_id: int, db: Session = Depends(get_db)) -> Response:
    item = db.get(CourseSkillCoverage, mapping_id)
    if not item or item.course_id != course_id: raise NotFoundError("未找到课程技能映射")
    plan_id = db.get(CurriculumCourse, course_id).plan_id; db.delete(item); db.flush(); CurriculumManagementService(db).refresh_plan_analyses(plan_id); db.commit()
    return Response(status_code=204)


@router.patch("/skill-mappings/{mapping_id}", response_model=CourseSkillMappingRead)
def update_course_skill_mapping_alias(mapping_id: int, payload: CourseSkillMappingWrite, db: Session = Depends(get_db)) -> CourseSkillCoverage:
    item = db.get(CourseSkillCoverage, mapping_id)
    if not item: raise NotFoundError("未找到课程技能映射")
    result = CurriculumManagementService(db).upsert_mapping(item.course_id, payload.model_dump(), mapping_id)
    db.commit(); return result


@router.delete("/skill-mappings/{mapping_id}", status_code=204)
def delete_course_skill_mapping_alias(mapping_id: int, db: Session = Depends(get_db)) -> Response:
    item = db.get(CourseSkillCoverage, mapping_id)
    if not item: raise NotFoundError("未找到课程技能映射")
    plan_id = db.get(CurriculumCourse, item.course_id).plan_id
    db.delete(item); db.flush(); CurriculumManagementService(db).refresh_plan_analyses(plan_id); db.commit()
    return Response(status_code=204)


@router.post("/analyses", status_code=201)
def create_curriculum_analysis(payload: CurriculumAnalysisCreate, db: Session = Depends(get_db)) -> dict:
    service = CurriculumManagementService(db)
    # Re-analysis is an idempotent upsert for the selected professional scope.
    # This prevents double-clicks/retries from creating parallel analysis rows
    # while still rebuilding the latest coverage snapshot in place.
    existing = db.execute(
        select(CurriculumAnalysis)
        .where(
            CurriculumAnalysis.job_id == payload.job_id,
            CurriculumAnalysis.plan_id == payload.plan_id,
            CurriculumAnalysis.graph_id == payload.graph_id,
        )
        .order_by(CurriculumAnalysis.updated_at.desc())
    ).scalars().first()
    analysis = service.build_analysis(**payload.model_dump(), existing=existing)
    db.commit()
    return service.analysis_payload(analysis)


@router.get("/analyses", status_code=200)
def get_curriculum_analysis_by_scope(
    job_id: str = Query(...), plan_id: str = Query(...), graph_id: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    """Return the latest analysis for the shared professional scope.

    The UI can therefore refresh after a teacher edits a mapping without
    having to know the opaque analysis id.
    """
    analysis = db.execute(
        select(CurriculumAnalysis)
        .where(CurriculumAnalysis.job_id == job_id, CurriculumAnalysis.plan_id == plan_id, CurriculumAnalysis.graph_id == graph_id)
        .order_by(CurriculumAnalysis.updated_at.desc())
    ).scalars().first()
    if not analysis:
        raise NotFoundError("该岗位、培养方案和能力图谱尚未创建对标分析")
    return CurriculumManagementService(db).analysis_payload(analysis)


@router.get("/analyses/{analysis_id}")
def get_curriculum_analysis(analysis_id: str, db: Session = Depends(get_db)) -> dict:
    analysis = db.get(CurriculumAnalysis, analysis_id)
    if not analysis: raise NotFoundError(f"未找到课程对标分析：{analysis_id}")
    return CurriculumManagementService(db).analysis_payload(analysis)


@router.get("/analyses/{analysis_id}/skills/{skill_code}")
def get_skill_coverage_evidence(analysis_id: str, skill_code: str, db: Session = Depends(get_db)) -> dict:
    analysis = db.get(CurriculumAnalysis, analysis_id)
    row = db.execute(select(SkillCoverage).where(SkillCoverage.analysis_id == analysis_id, SkillCoverage.skill_code == skill_code)).scalar_one_or_none()
    if not analysis or not row: raise NotFoundError("未找到技能覆盖证据")
    return {"analysis_id": analysis_id, "skill_code": skill_code, "coverage_status": row.coverage_status, "evidence": row.evidence, "demand_frequency": row.demand_frequency, "posting_count": row.posting_count, "mastery_level": row.mastery_level}


@router.get("/evidence")
def get_skill_coverage_evidence_by_scope(
    job_id: str = Query(...), plan_id: str = Query(...), graph_id: str = Query(...), skill_code: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    analysis = db.execute(select(CurriculumAnalysis).where(CurriculumAnalysis.job_id == job_id, CurriculumAnalysis.plan_id == plan_id, CurriculumAnalysis.graph_id == graph_id).order_by(CurriculumAnalysis.updated_at.desc())).scalars().first()
    if not analysis:
        raise NotFoundError("尚未创建课程对标分析")
    row = db.execute(select(SkillCoverage).where(SkillCoverage.analysis_id == analysis.id, SkillCoverage.skill_code == skill_code)).scalar_one_or_none()
    if not row:
        raise NotFoundError("未找到技能覆盖证据")
    # Expand the compact course evidence with the originating JD snippets.
    from app.models.job_market import JobPosting, JobPostingSkill
    course_evidence = [{"course_name": item.get("course_name", item.get("course_id", "")), "quote": item.get("quote", ""), "page": item.get("page"), "chunk_id": item.get("chunk_id")} for item in (row.evidence or [])]
    from app.models.competency import CompetencyNode
    graph_node = db.execute(select(CompetencyNode).where(CompetencyNode.graph_id == analysis.graph_id, CompetencyNode.skill_code == skill_code).order_by(CompetencyNode.mastery_level.desc())).scalars().first()
    job_evidence = []
    from app.core.enums import DataFlag
    for posting, link in db.execute(select(JobPosting, JobPostingSkill).join(JobPostingSkill, JobPostingSkill.posting_id == JobPosting.id).where(JobPosting.job_id == job_id, JobPosting.data_flag == DataFlag.REAL, JobPostingSkill.skill_code == skill_code).limit(20)).all():
        job_evidence.append({"title": posting.title, "quote": link.evidence_span or posting.raw_text[:400], "source_url": posting.source_url})
    return {"analysis_id": analysis.id, "skill_code": skill_code, "coverage_status": row.coverage_status, "job_evidence": job_evidence, "graph_evidence": ({"node_name": graph_node.name, "mastery_level": graph_node.mastery_level, "node_id": graph_node.id, "evidence": graph_node.evidence} if graph_node else None), "course_evidence": course_evidence}


@router.post("/analyses/{analysis_id}/optimizations", status_code=201)
def generate_optimization_run(analysis_id: str, db: Session = Depends(get_db)) -> dict:
    service = CurriculumManagementService(db); run = service.generate_optimization(analysis_id); db.commit(); return service.run_payload(run)


@router.post("/optimization-runs", status_code=201)
def generate_optimization_by_scope(payload: CurriculumAnalysisCreate, db: Session = Depends(get_db)) -> dict:
    analysis = db.execute(select(CurriculumAnalysis).where(CurriculumAnalysis.job_id == payload.job_id, CurriculumAnalysis.plan_id == payload.plan_id, CurriculumAnalysis.graph_id == payload.graph_id).order_by(CurriculumAnalysis.updated_at.desc())).scalars().first()
    if not analysis:
        raise NotFoundError("请先完成课程对标分析")
    service = CurriculumManagementService(db); run = service.generate_optimization(analysis.id); db.commit(); return service.run_payload(run)


@router.get("/optimizations/{run_id}")
def get_optimization_run(run_id: str, status: str | None = Query(None), db: Session = Depends(get_db)) -> dict:
    run = db.get(OptimizationRun, run_id)
    if not run: raise NotFoundError(f"未找到优化运行：{run_id}")
    payload = CurriculumManagementService(db).run_payload(run)
    if status: payload["suggestions"] = [item for item in payload["suggestions"] if item["status"] == status]
    return payload


@router.get("/optimization-runs/latest")
def get_latest_optimization_by_scope(job_id: str = Query(...), plan_id: str = Query(...), graph_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    run = db.execute(select(OptimizationRun).where(OptimizationRun.job_id == job_id, OptimizationRun.plan_id == plan_id, OptimizationRun.graph_id == graph_id).order_by(OptimizationRun.created_at.desc())).scalars().first()
    if not run:
        raise NotFoundError("尚未生成优化建议")
    return CurriculumManagementService(db).run_payload(run)


@router.patch("/optimizations/{run_id}/suggestions/{suggestion_id}")
def update_optimization_suggestion(run_id: str, suggestion_id: str, payload: SuggestionPatch, db: Session = Depends(get_db)) -> dict:
    item = db.get(OptimizationSuggestion, suggestion_id)
    if not item or item.run_id != run_id: raise NotFoundError("未找到优化建议")
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes:
        item.status = changes["status"]
    for key in ("title", "content", "action_type", "teacher_note", "edited_by"):
        if key in changes: setattr(item, key, changes[key])
    db.commit(); run = db.get(OptimizationRun, run_id)
    return next(row for row in CurriculumManagementService(db).run_payload(run)["suggestions"] if row["id"] == suggestion_id)


@router.patch("/optimization-suggestions/{suggestion_id}")
def update_optimization_suggestion_alias(suggestion_id: str, payload: SuggestionAliasPatch, db: Session = Depends(get_db)) -> dict:
    item = db.get(OptimizationSuggestion, suggestion_id)
    if not item:
        raise NotFoundError("未找到优化建议")
    changes = payload.model_dump(exclude_unset=True)
    if "state" in changes: changes["status"] = changes.pop("state")
    if "suggestion" in changes: changes["content"] = changes.pop("suggestion")
    for key in ("status", "title", "content", "action_type", "teacher_note", "edited_by"):
        if key in changes: setattr(item, key, changes[key])
    db.commit()
    run = db.get(OptimizationRun, item.run_id)
    return next(row for row in CurriculumManagementService(db).run_payload(run)["suggestions"] if row["id"] == suggestion_id)


@router.get("/optimizations/{run_id}/report.docx")
def export_optimization_report(run_id: str, db: Session = Depends(get_db)) -> Response:
    run = db.get(OptimizationRun, run_id)
    if not run: raise NotFoundError(f"未找到优化运行：{run_id}")
    content = CurriculumManagementService(db).export_docx(run)
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="optimization-{run_id}.docx"'})


@router.get("/optimization-runs/{run_id}/report.docx")
def export_optimization_report_alias(run_id: str, db: Session = Depends(get_db)) -> Response:
    return export_optimization_report(run_id, db)
