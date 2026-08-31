"""图谱节点编辑 Schema（教师审核阶段使用）。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.core.enums import NodeType
from app.schemas.competency import GENERATABLE_TYPES


class NodeUpdateRequest(BaseModel):
    """局部更新。未提供的字段保持不变。

    用 `model_fields_set` 区分「没传」与「显式传 null」——
    教师要能把 description 清空，那和「不改」是两回事。
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    skill_code: str | None = Field(default=None, max_length=96)
    mastery_level: int | None = Field(default=None, ge=1, le=4)
    order_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _must_change_something(self) -> "NodeUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("未提供任何要修改的字段")
        return self


class NodeCreateRequest(BaseModel):
    """新增节点。教师补充模型遗漏的能力时使用。"""

    parent_id: str = Field(min_length=1, max_length=160)
    node_type: NodeType
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    skill_code: str | None = Field(default=None, max_length=96)
    mastery_level: int | None = Field(default=None, ge=1, le=4)

    @model_validator(mode="after")
    def _type_must_be_allowed(self) -> "NodeCreateRequest":
        if self.node_type not in GENERATABLE_TYPES:
            raise ValueError(
                f"不支持手工创建 {self.node_type.value} 类型节点，"
                f"可用类型：{sorted(t.value for t in GENERATABLE_TYPES)}"
            )
        return self
