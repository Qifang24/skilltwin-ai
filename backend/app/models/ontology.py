"""技能本体与岗位。

Skill 是全系统的**唯一 join key** 载体。岗位需求统计、课程覆盖度、
实训任务、测评题、学生能力向量，全部通过 skill_code 关联到这张表。
任何位置出现的技能名称都必须先经 SkillNormalizer 归一，否则
`Label Studio` / `LabelStudio` / `标注工具Label Studio` 会变成三个维度，
让 Gap Analysis 静默算错。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.enums import Provenance, SkillCategory, SkillStatus, db_enum


class Skill(Base, TimestampMixin):
    """规范技能条目（canonical skill registry）。"""

    __tablename__ = "skill"

    #: 稳定 slug，形如 "tool.label_studio" / "prog.python" / "annot.bbox"
    skill_code: Mapped[str] = mapped_column(String(96), primary_key=True)

    name_zh: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[SkillCategory] = mapped_column(
        db_enum(SkillCategory, "skill_category"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)

    #: 归一化依据。所有已知别名、缩写、大小写/空格变体
    aliases: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )

    #: 该技能凭什么存在。[{"chunk_id", "page", "section", "quote"}]
    #: 与 CompetencyNode.evidence 同构，支撑「这个技能点的依据是什么」的下钻。
    #: 从职业标准抽取的技能，此处引文均已通过程序核验为原文精确子串。
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )

    status: Mapped[SkillStatus] = mapped_column(
        db_enum(SkillStatus, "skill_status"),
        default=SkillStatus.ACTIVE,
        nullable=False,
    )
    provenance: Mapped[Provenance] = mapped_column(
        db_enum(Provenance, "skill_provenance"),
        default=Provenance.HUMAN_AUTHORED,
        nullable=False,
    )
    #: 被 deprecate 时指向替代技能，保证历史数据仍可解析
    superseded_by: Mapped[str | None] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="SET NULL")
    )

    __table_args__ = (Index("ix_skill_category_status", "category", "status"),)

    def __repr__(self) -> str:
        return f"<Skill {self.skill_code} {self.name_zh}>"


class Job(Base, TimestampMixin):
    """岗位。第一版聚焦 ai_data_annotator，架构支持横向扩展。"""

    __tablename__ = "job"

    #: 稳定 slug，形如 "ai_data_annotator"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    job_family: Mapped[str | None] = mapped_column(String(128))
    industry: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)

    #: 对应的专业群，如「人工智能技术应用专业群」
    profession_group: Mapped[str | None] = mapped_column(String(128))

    #: 关联的国家职业分类大典编码等（有则填，无则留空，禁止编造）
    occupation_code: Mapped[str | None] = mapped_column(String(64))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    graphs: Mapped[list["CompetencyGraph"]] = relationship(  # noqa: F821
        back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job {self.id} {self.name}>"
