"""模型调用审计相关 Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EvidenceType, LLMRunStatus


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim: str
    marker: str | None = None
    evidence_type: EvidenceType
    chunk_id: str | None = None
    posting_id: str | None = None
    quote: str | None = None
    relevance: float | None = None
    verified: bool
    verifier_note: str | None = None


class LLMRunSummary(BaseModel):
    """列表视图：不含原始输出，避免响应体过大。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    agent: str
    provider: str
    model: str
    status: LLMRunStatus
    cache_hit: bool
    repair_attempts: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    created_at: datetime


class LLMRunDetail(LLMRunSummary):
    """详情视图：可解释性下钻的终点，能看到模型到底吃进去什么、吐出来什么。"""

    prompt_hash: str
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] | None = None
    raw_output: str | None = None
    error_message: str | None = None
    citations: list[CitationRead] = Field(default_factory=list)
