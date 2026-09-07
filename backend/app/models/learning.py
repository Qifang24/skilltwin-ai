"""个性化学习路径（Module 4 下半）。

**顺序由确定性算法决定，不是模型排的。**
先按前置依赖做拓扑排序，同层内按能力差距从大到小排 ——
这样「先学 A 再学 B」是有依据的，而不是模型觉得应该这样。
LLM 只负责写每个阶段的说明与资源推荐。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
from app.core.enums import PathItemType, PathStatus, db_enum


class LearningPath(Base, TimestampMixin):
    __tablename__ = "learning_path"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    student_id: Mapped[str] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    #: 依据哪份能力画像生成。画像更新后可重新生成路径，形成自适应闭环
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("skill_profile.id", ondelete="SET NULL")
    )
    graph_id: Mapped[str | None] = mapped_column(
        ForeignKey("competency_graph.id", ondelete="SET NULL")
    )

    title: Mapped[str | None] = mapped_column(String(255))
    #: LLM 写的整体说明。**不含顺序决策** —— 顺序是算出来的
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PathStatus] = mapped_column(
        db_enum(PathStatus, "path_status"), default=PathStatus.ACTIVE, nullable=False
    )
    #: 排序依据的说明，如「按前置依赖拓扑排序，同层按差距降序」
    ordering_method: Mapped[str | None] = mapped_column(String(128))
    #: 生成时的提示，如「3 项技能证据不足，其优先级仅供参考」
    warnings: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    generation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("llm_run.id", ondelete="SET NULL")
    )

    phases: Mapped[list["LearningPathPhase"]] = relationship(
        back_populates="path",
        cascade="all, delete-orphan",
        order_by="LearningPathPhase.order_index",
    )

    __table_args__ = (Index("ix_path_student_status", "student_id", "status"),)

    def __repr__(self) -> str:
        return f"<LearningPath {self.id} {self.status}>"


class LearningPathPhase(Base, TimestampMixin):
    """学习阶段。一个阶段聚焦一组可并行学习的技能。"""

    __tablename__ = "learning_path_phase"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    path_id: Mapped[str] = mapped_column(
        ForeignKey("learning_path.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: 本阶段要补的技能
    target_skill_codes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    est_hours: Mapped[float | None] = mapped_column(Float)
    status: Mapped[PathStatus] = mapped_column(
        db_enum(PathStatus, "phase_status"), default=PathStatus.ACTIVE, nullable=False
    )
    #: 该阶段被排在此处的确定性依据（拓扑层号、差距值）
    ordering_note: Mapped[str | None] = mapped_column(Text)

    path: Mapped[LearningPath] = relationship(back_populates="phases")
    items: Mapped[list["LearningPathItem"]] = relationship(
        back_populates="phase",
        cascade="all, delete-orphan",
        order_by="LearningPathItem.order_index",
    )

    __table_args__ = (
        UniqueConstraint("path_id", "order_index", name="uq_phase_order"),
    )

    def __repr__(self) -> str:
        return f"<LearningPathPhase {self.order_index} {self.title}>"


class LearningPathItem(Base, TimestampMixin):
    """阶段内的一个学习项：知识点、实训任务或复测。"""

    __tablename__ = "learning_path_item"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    phase_id: Mapped[str] = mapped_column(
        ForeignKey("learning_path_phase.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    item_type: Mapped[PathItemType] = mapped_column(
        db_enum(PathItemType, "path_item_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: 指向实际资源：training_task.id / knowledge_chunk.id 等。
    #: 无对应资源时留空 —— 不编造一个不存在的链接
    ref_id: Mapped[str | None] = mapped_column(String(96))
    skill_code: Mapped[str | None] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="SET NULL")
    )

    status: Mapped[PathStatus] = mapped_column(
        db_enum(PathStatus, "item_status"), default=PathStatus.ACTIVE, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    phase: Mapped[LearningPathPhase] = relationship(back_populates="items")
    activities: Mapped[list["LearningPathActivity"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="LearningPathActivity.created_at",
    )

    __table_args__ = (Index("ix_path_item_phase", "phase_id", "order_index"),)

    def __repr__(self) -> str:
        return f"<LearningPathItem {self.item_type} {self.title}>"


class LearningPathActivity(Base, TimestampMixin):
    """学习项状态变化的审计记录。

    点击“完成实训”只会写学习记录，不会伪造能力提升；只有关联复测完成判分后，
    才会产生新的能力画像并触发路径重算。
    """

    __tablename__ = "learning_path_activity"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("learning_path_item.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    previous_status: Mapped[PathStatus | None] = mapped_column(
        db_enum(PathStatus, "activity_previous_status")
    )
    new_status: Mapped[PathStatus | None] = mapped_column(
        db_enum(PathStatus, "activity_new_status")
    )
    ref_type: Mapped[str | None] = mapped_column(String(48))
    ref_id: Mapped[str | None] = mapped_column(String(96))
    note: Mapped[str | None] = mapped_column(Text)

    item: Mapped[LearningPathItem] = relationship(back_populates="activities")

    __table_args__ = (
        Index("ix_path_activity_item_time", "item_id", "created_at"),
        Index("ix_path_activity_ref", "ref_type", "ref_id"),
    )

    def __repr__(self) -> str:
        return f"<LearningPathActivity {self.action} {self.item_id}>"
