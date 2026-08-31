"""课程 Gap Analysis 的外部契约。"""

from pydantic import BaseModel, Field


class CourseEvidenceRead(BaseModel):
    course_id: str
    course_name: str
    total_hours: int | None = None
    coverage_strength: int = Field(ge=1, le=2)
    source_chunk_id: str
    source_page: str | None = None
    evidence_quote: str


class CurriculumSkillGapRead(BaseModel):
    skill_code: str
    skill_name: str
    demand_frequency: float | None = None
    coverage_strength: int = Field(ge=0, le=2)
    coverage_ratio: float = Field(ge=0, le=1)
    status: str
    courses: list[CourseEvidenceRead] = Field(default_factory=list)
    recommendation: str


class CurriculumQualityRead(BaseModel):
    plan_id: str
    plan_name: str
    source_name: str
    source_url: str | None = None
    is_partial: bool
    course_count: int
    mapped_skill_count: int
    market_is_reliable: bool
    warnings: list[str] = Field(default_factory=list)


class CurriculumGapDashboardRead(BaseModel):
    job_id: str
    job_name: str
    data_quality: CurriculumQualityRead
    skills: list[CurriculumSkillGapRead]
    reasoning_summary: str


class CurriculumOptimizationRecommendationRead(BaseModel):
    skill_code: str
    skill_name: str
    priority_score: float = Field(ge=0, le=100)
    action_type: str
    title: str
    suggestion: str
    demand_frequency: float
    coverage_status: str
    course_evidence: list[CourseEvidenceRead] = Field(default_factory=list)
    reasoning_summary: str


class CurriculumOptimizationRead(BaseModel):
    job_id: str
    plan_id: str
    recommendations: list[CurriculumOptimizationRecommendationRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reasoning_summary: str
