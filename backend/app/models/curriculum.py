"""课程方案与可审计的技能覆盖映射（Phase 11）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class CurriculumPlan(Base, TimestampMixin):
    __tablename__ = "curriculum_plan"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profession: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[str | None] = mapped_column(String(64))
    source_doc_id: Mapped[str | None] = mapped_column(String(96))
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    license_note: Mapped[str | None] = mapped_column(Text)
    #: 尚未完整结构化的方案不能被误说成“全部课程均已核验”。
    is_partial: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CurriculumCourse(Base, TimestampMixin):
    __tablename__ = "curriculum_course"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("curriculum_plan.id", ondelete="CASCADE"), nullable=False)
    course_code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))
    total_hours: Mapped[int | None] = mapped_column(Integer)
    source_chunk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_page: Mapped[str | None] = mapped_column(String(64))
    source_quote: Mapped[str] = mapped_column(Text, nullable=False)
    objectives: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    teaching_content: Mapped[str | None] = mapped_column(Text)
    knowledge_points: Mapped[str | None] = mapped_column(Text)
    practical_content: Mapped[str | None] = mapped_column(Text)
    learning_outcomes: Mapped[str | None] = mapped_column(Text)
    field_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (UniqueConstraint("plan_id", "name", name="uq_curriculum_course_name"), Index("ix_curriculum_course_plan", "plan_id"))


class CourseSkillCoverage(Base, TimestampMixin):
    __tablename__ = "course_skill_coverage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("curriculum_course.id", ondelete="CASCADE"), nullable=False)
    skill_code: Mapped[str] = mapped_column(ForeignKey("skill.skill_code", ondelete="RESTRICT"), nullable=False)
    #: 1=正文明确提及，2=课程能力目标要求实践；并非学习成效的测量值。
    coverage_strength: Mapped[int] = mapped_column(Integer, nullable=False)
    source_chunk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_page: Mapped[str | None] = mapped_column(String(64))
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_status: Mapped[str] = mapped_column(String(32), default="partial", nullable=False)
    origin: Mapped[str] = mapped_column(String(32), default="rule", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    generation_run_id: Mapped[str | None] = mapped_column(ForeignKey("llm_run.id", ondelete="SET NULL"))
    teacher_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_by: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (UniqueConstraint("course_id", "skill_code", name="uq_course_skill"), Index("ix_course_skill_skill", "skill_code"))


class CurriculumImportBatch(Base, TimestampMixin):
    __tablename__ = "curriculum_import_batch"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="parsed", nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    license_note: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    document_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confirmed_plan_id: Mapped[str | None] = mapped_column(String(96))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CurriculumDraftCourse(Base, TimestampMixin):
    __tablename__ = "curriculum_draft_course"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("curriculum_import_batch.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    field_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="valid", nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (UniqueConstraint("batch_id", "row_number", name="uq_curriculum_draft_row"),)


class CurriculumAnalysis(Base, TimestampMixin):
    __tablename__ = "curriculum_analysis"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("curriculum_plan.id", ondelete="CASCADE"), nullable=False)
    graph_id: Mapped[str] = mapped_column(ForeignKey("competency_graph.id", ondelete="RESTRICT"), nullable=False)
    snapshot_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class SkillCoverage(Base, TimestampMixin):
    __tablename__ = "skill_coverage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("curriculum_analysis.id", ondelete="CASCADE"), nullable=False)
    skill_code: Mapped[str] = mapped_column(ForeignKey("skill.skill_code", ondelete="RESTRICT"), nullable=False)
    coverage_status: Mapped[str] = mapped_column(String(32), nullable=False)
    coverage_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    demand_frequency: Mapped[float | None] = mapped_column(Float)
    posting_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mastery_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (UniqueConstraint("analysis_id", "skill_code", name="uq_analysis_skill_coverage"),)


class OptimizationRun(Base, TimestampMixin):
    __tablename__ = "optimization_run"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("curriculum_analysis.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("curriculum_plan.id", ondelete="CASCADE"), nullable=False)
    graph_id: Mapped[str] = mapped_column(ForeignKey("competency_graph.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    low_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    snapshot_version: Mapped[str] = mapped_column(String(128), nullable=False)


class OptimizationSuggestion(Base, TimestampMixin):
    __tablename__ = "optimization_suggestion"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("optimization_run.id", ondelete="CASCADE"), nullable=False)
    skill_code: Mapped[str] = mapped_column(ForeignKey("skill.skill_code", ondelete="RESTRICT"), nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    teacher_note: Mapped[str | None] = mapped_column(Text)
    edited_by: Mapped[str | None] = mapped_column(String(128))


class SuggestionEvidence(Base, TimestampMixin):
    __tablename__ = "suggestion_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suggestion_id: Mapped[str] = mapped_column(ForeignKey("optimization_suggestion.id", ondelete="CASCADE"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[str | None] = mapped_column(String(64))
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
