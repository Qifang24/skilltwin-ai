"""RAG 知识库。

分工：向量存 Chroma（key = chunk_id），元数据存这里。
**引用的唯一真源是 knowledge_chunk 表** —— Agent 输出里的每一条 [Sn] 标记
最终都要解析回一个真实存在的 chunk_id，否则视为无依据。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
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
from app.core.enums import SourceType, db_enum


class KnowledgeDoc(Base, TimestampMixin):
    """一篇入库文档。

    来源字段全部必须真实可核验。严禁伪造文献名、标准编号、页码——
    没有来源的内容一律不入库。
    """

    __tablename__ = "knowledge_doc"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)

    category: Mapped[str | None] = mapped_column(String(128))
    profession: Mapped[str | None] = mapped_column(String(128))
    job: Mapped[str | None] = mapped_column(String(64))

    # ---------- 来源（可核验，不可编造） ----------
    source_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        db_enum(SourceType, "source_type"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(1024))
    publisher: Mapped[str | None] = mapped_column(String(255))
    pub_year: Mapped[int | None] = mapped_column(Integer)
    #: 国家标准 / 行业标准编号，如 "GB/T xxxxx-xxxx"；无则留空
    standard_id: Mapped[str | None] = mapped_column(String(128))
    license_note: Mapped[str | None] = mapped_column(Text)

    #: 原文去重用，同时用于判断是否需要重新 ingest
    content_hash: Mapped[str | None] = mapped_column(String(64))
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="doc",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index",
    )

    __table_args__ = (
        Index("ix_doc_source_type", "source_type"),
        Index("ix_doc_job", "job"),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDoc {self.id} {self.title[:32]}>"


class KnowledgeChunk(Base, TimestampMixin):
    """检索与引用的最小单元。"""

    __tablename__ = "knowledge_chunk"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_doc.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    #: 页码 / 章节，引用时展示给用户核验
    page: Mapped[str | None] = mapped_column(String(64))
    section: Mapped[str | None] = mapped_column(String(512))

    #: 该 chunk 覆盖的规范技能，用于检索前的元数据过滤
    skill_codes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    token_count: Mapped[int | None] = mapped_column(Integer)

    #: 记录生成向量的模型，换模型后可据此判断哪些需要重建
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    #: Chroma 中的向量 id（MVP 阶段与 chunk id 一致，保留字段以便将来解耦）
    vector_id: Mapped[str | None] = mapped_column(String(96))

    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    doc: Mapped[KnowledgeDoc] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("doc_id", "chunk_index", name="uq_chunk_doc_index"),
        Index("ix_chunk_doc", "doc_id"),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeChunk {self.id} doc={self.doc_id}#{self.chunk_index}>"

    def citation_label(self) -> str:
        """给用户看的来源标签。"""
        parts = [self.doc.source_name] if self.doc else []
        if self.doc and self.doc.standard_id:
            parts.append(self.doc.standard_id)
        if self.section:
            parts.append(self.section)
        if self.page:
            parts.append(f"第{self.page}页")
        return " · ".join(p for p in parts if p)
