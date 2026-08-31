"""培养方案优化建议：只转换已验证的市场频率与课程 Gap，不调用 LLM。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.curriculum import CurriculumOptimizationRead, CurriculumOptimizationRecommendationRead
from app.services.curriculum_gap_service import CurriculumGapService


class CurriculumOptimizationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def generate(self, job_id: str, plan_id: str | None = None) -> CurriculumOptimizationRead:
        gap = CurriculumGapService(self._db).dashboard(job_id, plan_id)
        warnings = list(gap.data_quality.warnings)
        if not gap.data_quality.market_is_reliable:
            warnings.append("当前不生成按优先级排序的培养方案调整项：请导入不少于 30 条、不含 DEMO 的公开 JD 后重试。")
            return CurriculumOptimizationRead(job_id=job_id, plan_id=gap.data_quality.plan_id, warnings=warnings, reasoning_summary="优化建议需要可靠岗位需求频率与课程原文覆盖证据；当前仅能展示课程结构性覆盖。")
        rows: list[CurriculumOptimizationRecommendationRead] = []
        for item in gap.skills:
            if item.demand_frequency is None or item.coverage_strength >= 2:
                continue
            priority = round(item.demand_frequency * (1 - item.coverage_ratio) * 100, 1)
            if item.coverage_strength == 0:
                action, title = "add_or_embed_module", f"补充「{item.skill_name}」教学与实训模块"
                suggestion = "先由教师核查完整课程材料；确认缺失后，可在专业核心课或集中实训中新增该技能的规范、操作和成果评价。"
            else:
                action, title = "strengthen_practice_assessment", f"强化「{item.skill_name}」实践与评价"
                suggestion = "现有课程已提及该内容，但缺少明确实践目标；建议增加岗位情境任务、可提交成果与评分 Rubric。"
            rows.append(CurriculumOptimizationRecommendationRead(skill_code=item.skill_code, skill_name=item.skill_name, priority_score=priority, action_type=action, title=title, suggestion=suggestion, demand_frequency=item.demand_frequency, coverage_status=item.status, course_evidence=item.courses, reasoning_summary=f"岗位需求频率 {(item.demand_frequency * 100):.1f}% × 未覆盖比例 {(1 - item.coverage_ratio) * 100:.0f}% 得到优先级 {priority:.1f}。"))
        rows.sort(key=lambda item: (-item.priority_score, item.skill_code))
        return CurriculumOptimizationRead(job_id=job_id, plan_id=gap.data_quality.plan_id, recommendations=rows, warnings=warnings, reasoning_summary="优先级由可靠岗位需求频率与课程结构性未覆盖比例确定性计算；建议文本为规则模板，非模型结论。")
