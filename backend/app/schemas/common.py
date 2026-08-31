"""通用 Schema：Agent 响应信封、来源引用、分页、健康检查。

AgentEnvelope 是全系统所有 Agent 输出的统一外壳。任何一个专业性结论
返回给前端时都必须带上 sources / confidence / evidence_sufficiency，
让「依据是什么」成为接口契约的一部分，而不是可选的锦上添花。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EvidenceSufficiency, EvidenceType, SourceType

T = TypeVar("T")


class SourceRef(BaseModel):
    """一条可核验的证据引用。

    documentary 类必须能定位到 chunk_id；statistical 类必须能定位到 posting_id。
    前端据此渲染「【依据】」区块并支持下钻原文。
    """

    model_config = ConfigDict(from_attributes=True)

    type: EvidenceType
    #: 模型输出中的标记，如 "S3"
    marker: str | None = None

    chunk_id: str | None = None
    posting_id: str | None = None

    source_name: str | None = None
    source_type: SourceType | None = None
    standard_id: str | None = None
    page: str | None = None
    section: str | None = None
    url: str | None = None

    #: 原文摘录，供用户直接核验
    quote: str | None = None
    relevance: float | None = None
    verified: bool = False

    def label(self) -> str:
        parts = [p for p in (self.source_name, self.standard_id, self.section) if p]
        if self.page:
            parts.append(f"第{self.page}页")
        return " · ".join(parts)


class AgentEnvelope(BaseModel, Generic[T]):
    """所有 Agent 输出的统一信封。"""

    result: T
    #: 面向用户的简短决策依据。**不是** 模型内部思维链，只说明结论怎么来的
    reasoning_summary: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    #: 0–1，综合检索命中质量与结构校验结果
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.PARTIAL
    #: 前端据此显示「AI 生成」标识
    ai_generated: bool = True
    #: 可解释性下钻入口：GET /api/v1/llm-runs/{id}
    llm_run_id: str | None = None
    #: 低置信度、证据不足等需要提示用户的信息
    warnings: list[str] = Field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        return bool(self.sources)


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """所有 4xx/5xx 的统一错误体，与 core.errors 保持一致。"""

    error: ErrorDetail


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class ComponentHealth(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str = Field(description="ok | degraded")
    app: str
    version: str
    demo_mode: str
    components: list[ComponentHealth] = Field(default_factory=list)
