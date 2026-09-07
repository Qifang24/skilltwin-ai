"""岗位能力图谱 —— 全系统的数据中枢。

关键设计：图谱是**持久化本体**，不是每次请求由 LLM 现场生成的临时结构。
LLM 只产出 status=draft 的草案，教师审核后 approve 才成为 canonical。
只有这样，节点 ID 才稳定，课程映射 / 实训任务 / 学生能力向量才能长期关联，
两次 Skill Gap 才具备可比性。
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
from app.core.enums import EdgeRelation, GraphStatus, NodeType, db_enum


class CompetencyGraph(Base, TimestampMixin):
    """一个岗位的一个图谱版本。"""

    __tablename__ = "competency_graph"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[GraphStatus] = mapped_column(
        db_enum(GraphStatus, "graph_status"),
        default=GraphStatus.DRAFT,
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)

    #: 生成该草案的模型调用，用于可解释性下钻
    generation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("llm_run.id", ondelete="SET NULL")
    )
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped["Job"] = relationship(back_populates="graphs")  # noqa: F821
    nodes: Mapped[list["CompetencyNode"]] = relationship(
        back_populates="graph",
        cascade="all, delete-orphan",
        order_by="CompetencyNode.order_index",
    )

    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_graph_job_version"),
        Index("ix_graph_job_status", "job_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<CompetencyGraph {self.id} job={self.job_id} v{self.version} {self.status}>"


class CompetencyNode(Base, TimestampMixin):
    """图谱节点。树形结构由 parent_id 表达；跨层关系走 CompetencyEdge。"""

    __tablename__ = "competency_node"

    #: 稳定 slug，形如 "ai_annot.v1.cap.data_annotation"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    graph_id: Mapped[str] = mapped_column(
        ForeignKey("competency_graph.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("competency_node.id", ondelete="CASCADE")
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    node_type: Mapped[NodeType] = mapped_column(
        db_enum(NodeType, "node_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    #: 仅 skill_point / knowledge_point 必填 —— 学生能力向量的维度来源
    skill_code: Mapped[str | None] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="RESTRICT")
    )
    #: 掌握程度要求 1了解 2理解 3掌握 4熟练，同时作为 Target Skill Vector 的取值依据
    mastery_level: Mapped[int | None] = mapped_column(Integer)

    #: [{"chunk_id": ..., "quote": ..., "source_name": ..., "page": ...}]
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float)

    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    edited_by_human: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    graph: Mapped[CompetencyGraph] = relationship(back_populates="nodes")
    children: Mapped[list["CompetencyNode"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="CompetencyNode.order_index",
    )
    parent: Mapped["CompetencyNode | None"] = relationship(
        back_populates="children", remote_side=[id]
    )

    __table_args__ = (
        Index("ix_node_graph_parent", "graph_id", "parent_id"),
        Index("ix_node_graph_type", "graph_id", "node_type"),
        Index("ix_node_skill", "skill_code"),
    )

    def __repr__(self) -> str:
        return f"<CompetencyNode {self.id} {self.node_type} {self.name}>"


class CompetencyEdge(Base, TimestampMixin):
    """跨层关系。prereq 边是学习路径拓扑排序的依据（确定性计算，不经 LLM）。"""

    __tablename__ = "competency_edge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    graph_id: Mapped[str] = mapped_column(
        ForeignKey("competency_graph.id", ondelete="CASCADE"), nullable=False
    )
    from_node_id: Mapped[str] = mapped_column(
        ForeignKey("competency_node.id", ondelete="CASCADE"), nullable=False
    )
    to_node_id: Mapped[str] = mapped_column(
        ForeignKey("competency_node.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[EdgeRelation] = mapped_column(
        db_enum(EdgeRelation, "edge_relation"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "from_node_id", "to_node_id", "relation", name="uq_edge_triple"
        ),
        Index("ix_edge_graph_relation", "graph_id", "relation"),
    )

    def __repr__(self) -> str:
        return f"<CompetencyEdge {self.from_node_id} -{self.relation}-> {self.to_node_id}>"
