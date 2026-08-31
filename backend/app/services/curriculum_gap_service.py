"""课程结构性覆盖与岗位需求的确定性对标（Phase 11）。"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.curriculum import CourseSkillCoverage, CurriculumCourse, CurriculumPlan
from app.models.job_market import SkillDemandSnapshot
from app.models.ontology import Job, Skill
from app.schemas.curriculum import (
    CourseEvidenceRead,
    CurriculumGapDashboardRead,
    CurriculumQualityRead,
    CurriculumSkillGapRead,
)


class CurriculumGapService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def dashboard(self, job_id: str, plan_id: str | None = None) -> CurriculumGapDashboardRead:
        job = self._db.get(Job, job_id)
        if not job:
            raise NotFoundError(f"未找到岗位：{job_id}")
        plan_query = select(CurriculumPlan).where(CurriculumPlan.is_active.is_(True)).order_by(CurriculumPlan.id)
        if plan_id:
            plan_query = plan_query.where(CurriculumPlan.id == plan_id)
        plan = self._db.execute(plan_query).scalars().first()
        if not plan:
            raise NotFoundError("当前没有已导入的人才培养方案，请先导入带来源的课程数据。")

        courses = list(self._db.execute(select(CurriculumCourse).where(CurriculumCourse.plan_id == plan.id)).scalars())
        course_by_id = {course.id: course for course in courses}
        mappings = list(self._db.execute(select(CourseSkillCoverage).where(CourseSkillCoverage.course_id.in_(course_by_id) if course_by_id else False)).scalars())
        coverage: dict[str, list[CourseSkillCoverage]] = defaultdict(list)
        for item in mappings:
            coverage[item.skill_code].append(item)

        snapshots = list(self._db.execute(select(SkillDemandSnapshot).where(SkillDemandSnapshot.job_id == job_id, SkillDemandSnapshot.window_start.is_(None))).scalars())
        # DEMO 或小样本只可展示为数据质量信息，不能拿来给课程优化排序。
        market_reliable = bool(snapshots) and all(s.demo_posting_count == 0 and s.real_posting_count >= 30 for s in snapshots)
        demand = {item.skill_code: item.frequency for item in snapshots} if market_reliable else {}
        skill_codes = set(coverage) | set(demand)
        skills = {s.skill_code: s for s in self._db.execute(select(Skill).where(Skill.skill_code.in_(skill_codes))).scalars()} if skill_codes else {}

        warnings: list[str] = []
        if plan.is_partial:
            warnings.append("当前仅结构化了方案中的部分课程；未映射不等于该方案完全没有相关教学内容。")
        if not snapshots:
            warnings.append("当前没有岗位技能需求快照，以下仅展示课程结构性覆盖，不能按岗位需求排序。")
        elif not market_reliable:
            warnings.append("岗位样本含 DEMO 或真实样本少于 30 条，已停用需求频率排序，避免产生不稳健结论。")

        result: list[CurriculumSkillGapRead] = []
        for code in sorted(skill_codes, key=lambda value: (-(demand.get(value, -1)), value)):
            entries = coverage.get(code, [])
            strength = max((entry.coverage_strength for entry in entries), default=0)
            status = "unmapped" if strength == 0 else "practice" if strength == 2 else "introduced"
            if status == "unmapped":
                recommendation = "建议教师先核查完整课程材料；确认未覆盖后，再增设或嵌入对应教学与实训模块。"
            elif status == "introduced":
                recommendation = "课程正文已明确提及该技能；建议补充可评价的实践任务或考核证据。"
            else:
                recommendation = "课程能力目标已包含该技能；建议结合任务产出与考核记录继续验证实施强度。"
            result.append(CurriculumSkillGapRead(
                skill_code=code, skill_name=skills.get(code).name_zh if code in skills else code,
                demand_frequency=demand.get(code), coverage_strength=strength, coverage_ratio=strength / 2,
                status=status,
                courses=[CourseEvidenceRead(course_id=item.course_id, course_name=course_by_id[item.course_id].name, total_hours=course_by_id[item.course_id].total_hours, coverage_strength=item.coverage_strength, source_chunk_id=item.source_chunk_id, source_page=item.source_page, evidence_quote=item.evidence_quote) for item in entries],
                recommendation=recommendation,
            ))
        return CurriculumGapDashboardRead(
            job_id=job.id, job_name=job.name,
            data_quality=CurriculumQualityRead(plan_id=plan.id, plan_name=plan.name, source_name=plan.source_name, source_url=plan.source_url, is_partial=plan.is_partial, course_count=len(courses), mapped_skill_count=len(coverage), market_is_reliable=market_reliable, warnings=warnings),
            skills=result,
            reasoning_summary="课程覆盖仅依据已导入课程原文与映射证据；岗位需求频率只有在真实样本不少于 30 条且不含 DEMO 时才参与排序。",
        )
