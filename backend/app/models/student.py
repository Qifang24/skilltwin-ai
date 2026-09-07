"""学生、测评与能力画像（Module 4）。

合规要求：学生数据全部化名，不存真实个人信息，且必须支持彻底删除
（级联在此定义，DELETE /students/{id} 会带走全部关联数据）。

关于能力值的一条原则贯穿这里的设计：
**少量题目算不出精确能力值。** 因此 skill_profile_entry 除了点估计 score，
还存区间 [score_low, score_high]、置信度与证据条数 —— 前端据此在证据不足时
显示区间而非一个看起来很精确、实则站不住的数字。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.enums import (
    AssessmentStatus,
    AssessmentType,
    ItemType,
    ProfileSource,
    Provenance,
    db_enum,
)


class Student(Base, TimestampMixin):
    """学生。**只存化名**，不存姓名、学号、联系方式等真实个人信息。"""

    __tablename__ = "student"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: 化名，如「学生A」「测试用户01」
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    target_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("job.id", ondelete="SET NULL")
    )
    #: 年级/班级等非敏感的分组信息，可留空
    cohort: Mapped[str | None] = mapped_column(String(64))

    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    profiles: Mapped[list["SkillProfile"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Student {self.id} {self.display_name}>"


class AssessmentItem(Base, TimestampMixin):
    """题库中的一道题。"""

    __tablename__ = "assessment_item"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )

    stem: Mapped[str] = mapped_column(Text, nullable=False)
    item_type: Mapped[ItemType] = mapped_column(
        db_enum(ItemType, "item_type"), nullable=False
    )
    #: 选择题选项 [{"key":"A","text":"..."}]
    options: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    #: 正确答案。单选 ["A"]；多选 ["A","C"]；判断 ["true"]
    answer_key: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(Text)

    #: 0~1，越大越难。影响组卷时的难度分布
    difficulty: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    #: 命题依据，可溯源到知识库
    source_ref: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    provenance: Mapped[Provenance] = mapped_column(
        db_enum(Provenance, "item_provenance"),
        default=Provenance.LLM_DRAFTED,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    generation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("llm_run.id", ondelete="SET NULL")
    )

    skills: Mapped[list["AssessmentItemSkill"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_item_job_active", "job_id", "is_active"),)

    def __repr__(self) -> str:
        return f"<AssessmentItem {self.id} {self.item_type}>"


class AssessmentItemSkill(Base, TimestampMixin):
    """一道题考查哪些技能、各占多少权重。

    没有这张表，就无法把答题结果归因到具体能力维度 ——
    整个能力画像也就无从谈起。
    """

    __tablename__ = "assessment_item_skill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_item.id", ondelete="CASCADE"), nullable=False
    )
    skill_code: Mapped[str] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="RESTRICT"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    item: Mapped[AssessmentItem] = relationship(back_populates="skills")

    __table_args__ = (
        UniqueConstraint("item_id", "skill_code", name="uq_item_skill"),
        Index("ix_item_skill_code", "skill_code"),
    )


class Assessment(Base, TimestampMixin):
    """一次测评。"""

    __tablename__ = "assessment"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    student_id: Mapped[str] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[AssessmentType] = mapped_column(
        db_enum(AssessmentType, "assessment_type"),
        default=AssessmentType.DIAGNOSTIC,
        nullable=False,
    )
    status: Mapped[AssessmentStatus] = mapped_column(
        db_enum(AssessmentStatus, "assessment_status"),
        default=AssessmentStatus.IN_PROGRESS,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[Student] = relationship(back_populates="assessments")
    responses: Mapped[list["AssessmentResponse"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_assessment_student", "student_id", "status"),)

    def __repr__(self) -> str:
        return f"<Assessment {self.id} {self.type} {self.status}>"


class AssessmentResponse(Base, TimestampMixin):
    """学生对一道题的作答。"""

    __tablename__ = "assessment_response"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessment.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_item.id", ondelete="CASCADE"), nullable=False
    )
    response: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    #: 0~1。客观题非 0 即 1，主观题可给部分分
    score: Mapped[float | None] = mapped_column(Float)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assessment: Mapped[Assessment] = relationship(back_populates="responses")

    __table_args__ = (
        UniqueConstraint("assessment_id", "item_id", name="uq_response_item"),
    )


class SkillProfile(Base, TimestampMixin):
    """一次能力画像快照。

    每次测评或实训评分后新建一份，不覆盖旧的 —— 能力变化轨迹本身就是
    自适应学习闭环要展示的东西。
    """

    __tablename__ = "skill_profile"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    student_id: Mapped[str] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("job.id", ondelete="SET NULL")
    )
    source: Mapped[ProfileSource] = mapped_column(
        db_enum(ProfileSource, "profile_source"),
        default=ProfileSource.DIAGNOSTIC,
        nullable=False,
    )
    #: 产生该画像的测评（若来自实训则为空）
    assessment_id: Mapped[str | None] = mapped_column(
        ForeignKey("assessment.id", ondelete="SET NULL")
    )
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[Student] = relationship(back_populates="profiles")
    entries: Mapped[list["SkillProfileEntry"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_profile_student_time", "student_id", "computed_at"),)

    def as_vector(self) -> dict[str, float]:
        return {e.skill_code: e.score for e in self.entries}

    def __repr__(self) -> str:
        return f"<SkillProfile {self.id} {self.source}>"


class SkillProfileEntry(Base, TimestampMixin):
    """单个技能维度的能力估计。

    **不只存一个数**：少量题目算不出精确能力值，因此同时存
    区间与证据条数。前端在 confidence 低时应显示区间而非点估计 ——
    「Label Studio: 20 分」这种看似精确实则站不住的数字，
    比不给数字更有害。
    """

    __tablename__ = "skill_profile_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("skill_profile.id", ondelete="CASCADE"), nullable=False
    )
    skill_code: Mapped[str] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="RESTRICT"), nullable=False
    )

    #: 点估计 0~100
    score: Mapped[float] = mapped_column(Float, nullable=False)
    #: 95% 置信区间下界/上界（Wilson 区间）
    score_low: Mapped[float] = mapped_column(Float, nullable=False)
    score_high: Mapped[float] = mapped_column(Float, nullable=False)
    #: 0~1，由区间宽度导出：区间越窄越可信
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    #: 支撑该估计的作答数（加权后的有效题数）
    evidence_count: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    #: 估计方法，便于日后换算法时区分历史数据
    method: Mapped[str] = mapped_column(String(64), default="wilson", nullable=False)

    profile: Mapped[SkillProfile] = relationship(back_populates="entries")

    __table_args__ = (
        UniqueConstraint("profile_id", "skill_code", name="uq_profile_skill"),
        Index("ix_profile_entry_skill", "skill_code"),
    )

    @property
    def is_reliable(self) -> bool:
        """置信度过低时前端应显示区间而非点估计。"""
        return self.confidence >= 0.5

    def __repr__(self) -> str:
        return f"<SkillProfileEntry {self.skill_code} {self.score:.0f}±>"
