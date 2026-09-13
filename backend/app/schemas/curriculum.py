"""课程导入、对标与优化的外部契约。"""

from datetime import datetime
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


class CurriculumImportConfirmRequest(BaseModel):
    plan_id: str = Field(min_length=2, max_length=96)
    name: str = Field(min_length=2, max_length=255)
    profession: str | None = None
    version: str | None = None
    is_partial: bool = False


class CurriculumImportBatchRead(BaseModel):
    id: str
    filename: str
    status: str
    source_name: str
    source_url: str | None = None
    license_note: str | None = None
    error_message: str | None = None
    confirmed_plan_id: str | None = None
    courses: list[dict] = Field(default_factory=list)


class CurriculumPlanWrite(BaseModel):
    id: str = Field(min_length=2, max_length=96)
    name: str = Field(min_length=2, max_length=255)
    profession: str | None = None
    version: str | None = None
    source_name: str = Field(min_length=1, max_length=255)
    source_url: str | None = None
    license_note: str | None = None
    is_partial: bool = True
    is_active: bool = True


class CurriculumPlanRead(CurriculumPlanWrite):
    course_count: int = 0
    model_config = {"from_attributes": True}


class CurriculumCourseWrite(BaseModel):
    id: str | None = None
    course_code: str | None = None
    name: str = Field(min_length=1, max_length=255)
    category: str | None = None
    total_hours: int | None = Field(default=None, ge=0)
    objectives: str | None = None
    description: str | None = None
    teaching_content: str | None = None
    knowledge_points: str | None = None
    practical_content: str | None = None
    learning_outcomes: str | None = None
    source_chunk_id: str = "manual"
    source_page: str | None = None
    source_quote: str


class CurriculumCourseRead(CurriculumCourseWrite):
    id: str
    plan_id: str
    field_evidence: dict = Field(default_factory=dict)
    model_config = {"from_attributes": True}


class CourseSkillMappingWrite(BaseModel):
    skill_code: str
    coverage_status: str = Field(pattern="^(covered|partial|uncovered)$")
    # Uncovered mappings legitimately have no course quote; covered/partial
    # mappings are still mechanically checked by the service.
    evidence_quote: str = Field(default="")
    source_chunk_id: str = "manual"
    source_page: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None
    teacher_confirmed: bool = False
    edited_by: str | None = None


class CourseSkillMappingRead(CourseSkillMappingWrite):
    id: int
    course_id: str
    origin: str
    coverage_strength: int
    model_config = {"from_attributes": True}


class CurriculumAnalysisCreate(BaseModel):
    job_id: str
    plan_id: str
    graph_id: str


class SkillCoverageRead(BaseModel):
    skill_code: str
    skill_name: str | None = None
    coverage_status: str
    coverage_ratio: float
    demand_frequency: float | None = None
    posting_count: int
    mastery_level: int
    evidence: list[dict] = Field(default_factory=list)


class CurriculumAnalysisRead(BaseModel):
    id: str
    job_id: str
    plan_id: str
    graph_id: str
    snapshot_version: str
    status: str
    metrics: dict
    skills: list[SkillCoverageRead] = Field(default_factory=list)


class OptimizationRunCreate(BaseModel):
    analysis_id: str


class SuggestionPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|adopted|ignored)$")
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    action_type: str | None = Field(default=None, min_length=1, max_length=64)
    teacher_note: str | None = None
    edited_by: str | None = None


class SuggestionAliasPatch(BaseModel):
    state: str | None = Field(default=None, pattern="^(pending|adopted|ignored)$")
    title: str | None = Field(default=None, min_length=1, max_length=255)
    suggestion: str | None = Field(default=None, min_length=1)
    action_type: str | None = Field(default=None, min_length=1, max_length=64)
    teacher_note: str | None = None
    edited_by: str | None = None


class SuggestionRead(BaseModel):
    id: str
    run_id: str
    skill_code: str
    skill_name: str | None = None
    priority_score: float
    priority: str
    action_type: str
    title: str
    content: str
    status: str
    teacher_note: str | None = None
    evidence: list[dict] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class OptimizationRunRead(BaseModel):
    id: str
    analysis_id: str
    job_id: str
    plan_id: str
    graph_id: str
    status: str
    is_stale: bool
    low_sample: bool
    snapshot_version: str
    suggestions: list[SuggestionRead] = Field(default_factory=list)
