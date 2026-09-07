"""模型调用审计与引用记录。

这两张表同时承担三个职责，是「可解释性」不沦为口号的技术底座：
  1. 可复现   —— 输入输出全量落盘，任何结论都能复查
  2. 可演示   —— DEMO_MODE=replay 从这里回放真实产出，断网也能演示
  3. 可核验   —— citation 把每条结论锚定到真实 chunk_id / posting_id
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.enums import EvidenceType, LLMRunStatus, db_enum


class LLMRun(Base, TimestampMixin):
    """一次模型调用的完整记录。"""

    __tablename__ = "llm_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    #: (agent, model, 渲染后 prompt) 的哈希 —— 缓存与回放的键
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    #: 输入摘要（不存完整 prompt 以免膨胀；调试需要时可开 debug 落盘）
    input_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    #: 校验通过后的结构化输出，回放时直接复用
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    raw_output: Mapped[str | None] = mapped_column(Text)

    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[LLMRunStatus] = mapped_column(
        db_enum(LLMRunStatus, "llm_run_status"),
        default=LLMRunStatus.SUCCESS,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    #: 是否命中缓存（命中则未产生真实网络调用与费用）
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: 结构校验失败后的修复重试次数
    repair_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    citations: Mapped[list["Citation"]] = relationship(
        back_populates="llm_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_llmrun_cache", "agent", "model", "prompt_hash", "status"),
        Index("ix_llmrun_agent_created", "agent", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LLMRun {self.id} {self.agent} {self.status}>"


class Citation(Base, TimestampMixin):
    """一条结论 → 一份证据的锚定记录。

    documentary 类必须有 chunk_id；statistical 类必须有 posting_id。
    两者都没有的结论 = 无依据，VerificationService 会将其标为未验证并降置信度。
    """

    __tablename__ = "citation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    llm_run_id: Mapped[str] = mapped_column(
        ForeignKey("llm_run.id", ondelete="CASCADE"), nullable=False
    )

    #: 被支撑的具体论断
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    #: 模型输出里的标记序号，如 "S3"
    marker: Mapped[str | None] = mapped_column(String(16))

    evidence_type: Mapped[EvidenceType] = mapped_column(
        db_enum(EvidenceType, "evidence_type"), nullable=False
    )
    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_chunk.id", ondelete="SET NULL")
    )
    #: 统计类证据指向的岗位信息条目（Phase 10 建表后启用外键）
    posting_id: Mapped[str | None] = mapped_column(String(96))

    #: 证据原文摘录，前端直接展示供用户核验
    quote: Mapped[str | None] = mapped_column(Text)
    relevance: Mapped[float | None] = mapped_column(Float)

    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verifier_note: Mapped[str | None] = mapped_column(Text)

    llm_run: Mapped[LLMRun] = relationship(back_populates="citations")

    __table_args__ = (
        Index("ix_citation_run", "llm_run_id"),
        Index("ix_citation_chunk", "chunk_id"),
    )

    def __repr__(self) -> str:
        return f"<Citation {self.id} {self.evidence_type} verified={self.verified}>"
