from sqlalchemy.orm import Session

from app.models.curriculum import CourseSkillCoverage, CurriculumCourse, CurriculumPlan
from app.models.job_market import SkillDemandSnapshot
from app.models.ontology import Job, Skill
from app.core.enums import SkillCategory
from app.services.curriculum_gap_service import CurriculumGapService
from app.services.curriculum_optimization_service import CurriculumOptimizationService


def _base(db: Session, *, reliable: bool) -> None:
    db.add(Job(id="ai_data_annotator", name="AI数据标注工程师"))
    db.add_all([
        Skill(skill_code="data.cleaning", name_zh="数据清洗", category=SkillCategory.DATA),
        Skill(skill_code="quality.audit", name_zh="标注数据审核", category=SkillCategory.QUALITY),
    ])
    db.flush()
    db.add(CurriculumPlan(id="plan", name="公开方案节选", source_name="公开来源", is_partial=True))
    db.flush()
    db.add(CurriculumCourse(id="course", plan_id="plan", name="数据分析与处理", total_hours=64, source_chunk_id="doc#1", source_quote="课程名称：数据分析与处理"))
    db.flush()
    db.add(CourseSkillCoverage(course_id="course", skill_code="data.cleaning", coverage_strength=1, source_chunk_id="doc#1", evidence_quote="数据清洗"))
    db.add_all([
        SkillDemandSnapshot(job_id="ai_data_annotator", skill_code="data.cleaning", posting_count=32, total_postings=40, frequency=.8, real_posting_count=40 if reliable else 2, demo_posting_count=0 if reliable else 1),
        SkillDemandSnapshot(job_id="ai_data_annotator", skill_code="quality.audit", posting_count=28, total_postings=40, frequency=.7, real_posting_count=40 if reliable else 2, demo_posting_count=0 if reliable else 1),
    ])
    db.commit()


def test_gap_is_evidence_backed_and_uses_reliable_market_only(db: Session) -> None:
    _base(db, reliable=True)
    result = CurriculumGapService(db).dashboard("ai_data_annotator")
    assert result.data_quality.market_is_reliable is True
    assert result.skills[0].skill_code == "data.cleaning"
    cleaning = result.skills[0]
    assert cleaning.status == "introduced"
    assert cleaning.courses[0].evidence_quote == "数据清洗"
    audit = next(item for item in result.skills if item.skill_code == "quality.audit")
    assert audit.status == "unmapped"
    assert audit.demand_frequency == .7


def test_gap_refuses_demo_or_small_sample_market_ranking(db: Session) -> None:
    _base(db, reliable=False)
    result = CurriculumGapService(db).dashboard("ai_data_annotator")
    assert result.data_quality.market_is_reliable is False
    assert all(item.demand_frequency is None for item in result.skills)
    assert any("DEMO" in warning for warning in result.data_quality.warnings)


def test_optimization_prioritizes_evidence_backed_gaps_only(db: Session) -> None:
    _base(db, reliable=True)
    result = CurriculumOptimizationService(db).generate("ai_data_annotator")
    assert result.recommendations[0].skill_code == "quality.audit"
    assert result.recommendations[0].action_type == "add_or_embed_module"
    assert result.recommendations[0].priority_score == 70.0
    assert result.recommendations[1].skill_code == "data.cleaning"


def test_optimization_stops_when_market_is_unreliable(db: Session) -> None:
    _base(db, reliable=False)
    result = CurriculumOptimizationService(db).generate("ai_data_annotator")
    assert not result.recommendations
    assert any("不生成" in warning for warning in result.warnings)
