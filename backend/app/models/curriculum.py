"""课程方案与可审计的技能覆盖映射（Phase 11）。"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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

    __table_args__ = (UniqueConstraint("course_id", "skill_code", name="uq_course_skill"), Index("ix_course_skill_skill", "skill_code"))
