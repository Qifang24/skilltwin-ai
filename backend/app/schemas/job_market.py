"""岗位市场分析 API 契约（Phase 10）。

所有百分比来自 ``skill_demand_snapshot`` 的确定性统计；每个技能均携带可
下钻的 JD 原文片段。DEMO 样本不会被隐藏，而是显式返回给前端标识。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import DataFlag


class MarketDataQualityRead(BaseModel):
    total_postings: int = 0
    real_postings: int = 0
    demo_postings: int = 0
    postings_with_skills: int = 0
    extraction_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_posted_at: int = 0
    duplicate_raw_text_count: int = 0
    latest_posted_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class DemandEvidenceRead(BaseModel):
    posting_id: str
    title: str
    company_type: str | None = None
    city: str | None = None
    posted_at: datetime | None = None
    source_name: str | None = None
    source_url: str | None = None
    data_flag: DataFlag
    evidence_span: str


class SkillDemandRead(BaseModel):
    skill_code: str
    skill_name: str | None = None
    category: str | None = None
    posting_count: int
    total_postings: int
    frequency: float = Field(ge=0.0, le=1.0)
    real_posting_count: int
    demo_posting_count: int
    is_demo_contaminated: bool = False
    evidence: list[DemandEvidenceRead] = Field(default_factory=list)


class SkillTrendPointRead(BaseModel):
    window_start: datetime
    window_end: datetime
    posting_count: int
    total_postings: int
    frequency: float = Field(ge=0.0, le=1.0)
    real_posting_count: int
    demo_posting_count: int


class SkillTrendSeriesRead(BaseModel):
    skill_code: str
    skill_name: str | None = None
    points: list[SkillTrendPointRead] = Field(default_factory=list)


class JobMarketDashboardRead(BaseModel):
    job_id: str
    job_name: str
    data_quality: MarketDataQualityRead
    ranking: list[SkillDemandRead] = Field(default_factory=list)
    trends: list[SkillTrendSeriesRead] = Field(default_factory=list)
    computed_at: datetime | None = None
    analysis_method: str = "deterministic_rule_match"


class JobMarketAnalyzeResponse(BaseModel):
    dashboard: JobMarketDashboardRead
    extracted_skill_links: int = 0
    snapshots_written: int = 0
    reasoning_summary: str
    warnings: list[str] = Field(default_factory=list)


class JobPostingImportItem(BaseModel):
    id: str = Field(min_length=2, max_length=96)
    title: str = Field(min_length=2, max_length=255)
    raw_text: str = Field(min_length=40)
    source_name: str = Field(min_length=2, max_length=128)
    source_url: str = Field(min_length=8, max_length=1024)
    posted_at: datetime | None = None
    city: str | None = None
    company_type: str | None = None
    salary_text: str | None = None
    education_req: str | None = None
    experience_req: str | None = None
    data_flag: DataFlag = DataFlag.REAL


class JobPostingImportRequest(BaseModel):
    job_id: str = Field(default="ai_data_annotator", min_length=2, max_length=96)
    job_name: str = Field(default="AI 数据标注工程师", min_length=2, max_length=255)
    postings: list[JobPostingImportItem] = Field(min_length=1, max_length=500)


class JobPostingImportResponse(BaseModel):
    created: int
    updated: int
    skipped_duplicates: int
    pii_scrubbed: int
    dashboard: JobMarketDashboardRead
