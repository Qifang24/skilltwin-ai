"""岗位能力图谱 Schema。

层级设计直接对齐《人工智能训练师国家职业技能标准》的表格结构：

    职业功能   →  competency        能力
    工作内容   →  competency_unit   能力单元
    技能要求   →  skill_point       技能点
    相关知识要求 → knowledge_point   知识点

这不是巧合 —— 职业标准本来就是按「能力如何分解」组织的，
顺着它的结构走，图谱才有据可依，而不是我们自己想象出来的分类。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import (
    GraphStatus,
    MasteryLevel,
    NodeType,
    SKILL_BEARING_NODE_TYPES,
)
from app.schemas.common import SourceRef

#: LLM 只允许生成这三层；job 根节点由服务端创建，不交给模型
GENERATABLE_TYPES = {
    NodeType.COMPETENCY,
    NodeType.COMPETENCY_UNIT,
    NodeType.SKILL_POINT,
    NodeType.KNOWLEDGE_POINT,
}


# ======================================================== LLM 草案输出
class NodeDraft(BaseModel):
    """模型生成的单个节点。

    刻意**不让模型生成 id** —— 模型给的 id 不稳定、易冲突，
    而节点 id 是下游课程映射、实训任务、学生能力向量的外键。
    id 由服务端确定性分配。
    """

    node_type: NodeType
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)

    #: 技能点/知识点必填，且必须是技能表里已存在的编码
    skill_code: str | None = Field(default=None, max_length=96)
    #: 1了解 2理解 3掌握 4熟练
    mastery_level: int | None = Field(default=None, ge=1, le=4)

    #: 引用的检索片段编号，如 ["S1", "S3"]
    evidence_markers: list[str] = Field(default_factory=list, max_length=6)

    children: list["NodeDraft"] = Field(default_factory=list, max_length=12)

    @field_validator("node_type")
    @classmethod
    def _must_be_generatable(cls, v: NodeType) -> NodeType:
        if v not in GENERATABLE_TYPES:
            raise ValueError(
                f"节点类型 {v.value} 不允许由模型生成，"
                f"可用类型：{sorted(t.value for t in GENERATABLE_TYPES)}"
            )
        return v

    @property
    def is_skill_bearing(self) -> bool:
        return self.node_type in SKILL_BEARING_NODE_TYPES


NodeDraft.model_rebuild()


class CompetencyGraphDraft(BaseModel):
    """一次生成的完整草案。"""

    summary: str = Field(default="", max_length=800)
    competencies: list[NodeDraft] = Field(min_length=2, max_length=10)


# ============================================================ 读取视图
class NodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None = None
    node_type: NodeType
    name: str
    description: str | None = None
    teacher_note: str | None = None
    skill_code: str | None = None
    mastery_level: int | None = None
    mastery_label: str | None = None
    order_index: int = 0
    confidence: float | None = None
    ai_generated: bool = True
    edited_by_human: bool = False
    evidence: list[dict] = Field(default_factory=list)
    children: list["NodeRead"] = Field(default_factory=list)

    @classmethod
    def from_node(cls, node, children: list["NodeRead"] | None = None) -> "NodeRead":  # noqa: ANN001
        item = cls.model_validate(node)
        item.mastery_label = (
            MasteryLevel(node.mastery_level).label_zh if node.mastery_level else None
        )
        item.children = children or []
        return item


NodeRead.model_rebuild()


class GraphSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    version: int
    status: GraphStatus
    title: str | None = None
    summary: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    selected_skill_codes: list[str] = Field(default_factory=list)
    created_at: datetime
    node_count: int = 0
    skill_point_count: int = 0


class GraphDetail(GraphSummary):
    """前端渲染用的完整嵌套结构。"""

    tree: list[NodeRead] = Field(default_factory=list)
    #: 生成时使用的依据，供「这份图谱凭什么这么画」下钻
    sources: list[SourceRef] = Field(default_factory=list)
    generation_run_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class GenerateGraphRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    #: 额外的侧重说明，例如「侧重图像标注方向」
    focus: str | None = Field(default=None, max_length=200)
    #: 从岗位需求分析中明确纳入本次图谱的技能；为空时使用全部有效技能。
    selected_skill_codes: list[str] = Field(default_factory=list, max_length=50)


class ApproveGraphRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=128, description="审核人姓名")
