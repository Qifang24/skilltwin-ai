"""混合检索：dense + BM25 → RRF 融合。

为什么用 RRF（Reciprocal Rank Fusion）而不是加权求和分数：
向量相似度与 BM25 分数量纲完全不同（前者 0~1，后者无上界且随语料变化），
直接加权需要反复调参且换语料就失效。RRF 只用**排名**不用分数，
天然免疫量纲问题，是工业界混合检索的稳妥默认。

    RRF(d) = Σ_r  1 / (k + rank_r(d))     k 默认 60
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.enums import EvidenceType
from app.core.logging import get_logger
from app.models.knowledge import KnowledgeChunk
from app.rag.bm25 import BM25Index
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.rag.vector_store import VectorStore, build_vector_store
from app.schemas.common import SourceRef

logger = get_logger(__name__)

BM25_INDEX_PATH = settings.data_dir / "bm25_knowledge.pkl"


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    #: 各通路的排名，便于排查「这条为什么被召回」
    dense_rank: int | None = None
    sparse_rank: int | None = None
    page: str | None = None
    section: str | None = None
    doc_id: str | None = None
    source_name: str | None = None
    standard_id: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    skill_codes: list[str] = field(default_factory=list)

    def to_source_ref(self, marker: str | None = None) -> SourceRef:
        return SourceRef(
            type=EvidenceType.DOCUMENTARY,
            marker=marker,
            chunk_id=self.chunk_id,
            source_name=self.source_name,
            standard_id=self.standard_id,
            page=self.page,
            section=self.section,
            url=self.source_url,
            quote=self.text[:300],
            relevance=self.score,
            verified=True,  # 出自真实入库 chunk，非模型编造
        )


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], k: int | None = None
) -> dict[str, float]:
    """把多路排序结果融合成一个总分。"""
    constant = k if k is not None else settings.rrf_k
    scores: dict[str, float] = {}
    for ranking in ranked_lists:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (constant + rank)
    return scores


class HybridRetriever:
    """知识库检索入口。"""

    def __init__(
        self,
        embedder: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        bm25: BM25Index | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = vector_store
        self._bm25 = bm25

    @property
    def embedder(self) -> EmbeddingProvider:
        if self._embedder is None:
            self._embedder = get_embedding_provider()
        return self._embedder

    @property
    def store(self) -> VectorStore:
        if self._store is None:
            self._store = build_vector_store()
        return self._store

    @property
    def bm25(self) -> BM25Index:
        if self._bm25 is None:
            self._bm25 = BM25Index.load(BM25_INDEX_PATH)
        return self._bm25

    def _sparse_index(self, db: Session) -> BM25Index:
        if self._bm25 is not None or settings.vector_store != "sql":
            return self.bm25
        rows = db.execute(select(KnowledgeChunk.id, KnowledgeChunk.text)).all()
        index = BM25Index()
        index.build([row.id for row in rows], [row.text for row in rows])
        return index

    def search(
        self,
        db: Session,
        query: str,
        *,
        top_n: int | None = None,
        dense_k: int | None = None,
        sparse_k: int | None = None,
        where: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []

        # 用 `is None` 而非 `or`：k=0 的语义是**关闭该通路**（评测时要单独跑单路），
        # 用 `or` 会让 0 回落成默认值，三种策略实际跑的是同一套，对比结果全无意义。
        final_n = settings.retrieve_final_top_n if top_n is None else top_n
        k_dense = settings.retrieve_dense_top_k if dense_k is None else dense_k
        k_sparse = settings.retrieve_sparse_top_k if sparse_k is None else sparse_k

        # ---- 通路 1：向量 ----
        dense_ids: list[str] = []
        if k_dense > 0:
            try:
                query_vector = self.embedder.embed_one(query, is_query=True)
                dense_hits = self.store.search(query_vector, k_dense, where=where)
                dense_ids = [hit.chunk_id for hit in dense_hits]
            except Exception as exc:  # 向量通路故障不应让整个检索瘫痪
                logger.warning("向量检索失败，退化为纯 BM25", extra={"error": str(exc)})

        # ---- 通路 2：BM25 ----
        sparse_ids: list[str] = []
        if k_sparse > 0:
            sparse_ids = [hit.chunk_id for hit in self._sparse_index(db).search(query, k_sparse)]

        if not dense_ids and not sparse_ids:
            return []

        # ---- RRF 融合 ----
        fused = reciprocal_rank_fusion([ids for ids in (dense_ids, sparse_ids) if ids])
        dense_rank = {cid: i + 1 for i, cid in enumerate(dense_ids)}
        sparse_rank = {cid: i + 1 for i, cid in enumerate(sparse_ids)}

        ordered = sorted(fused.items(), key=lambda item: item[1], reverse=True)

        # BM25 通路可能召回被元数据过滤排除的 chunk，这里统一按 where 再过滤一次
        candidate_ids = [cid for cid, _ in ordered]
        chunks = self._load_chunks(db, candidate_ids, where=where)

        results: list[RetrievedChunk] = []
        for chunk_id, score in ordered:
            chunk = chunks.get(chunk_id)
            if chunk is None:
                continue
            doc = chunk.doc
            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=chunk.text,
                    score=score,
                    dense_rank=dense_rank.get(chunk_id),
                    sparse_rank=sparse_rank.get(chunk_id),
                    page=chunk.page,
                    section=chunk.section,
                    doc_id=chunk.doc_id,
                    source_name=doc.source_name if doc else None,
                    standard_id=doc.standard_id if doc else None,
                    source_type=doc.source_type.value if doc else None,
                    source_url=doc.source_url if doc else None,
                    skill_codes=list(chunk.skill_codes or []),
                )
            )
            if len(results) >= final_n:
                break
        return results

    def _load_chunks(
        self, db: Session, chunk_ids: list[str], where: dict[str, Any] | None
    ) -> dict[str, KnowledgeChunk]:
        if not chunk_ids:
            return {}
        stmt = (
            select(KnowledgeChunk)
            .options(selectinload(KnowledgeChunk.doc))
            .where(KnowledgeChunk.id.in_(chunk_ids))
        )
        chunks = db.execute(stmt).scalars().all()

        if where:
            filtered = {}
            for chunk in chunks:
                doc = chunk.doc
                if doc is None:
                    continue
                ok = all(
                    getattr(doc, key, None) == value
                    or (key == "source_type" and doc.source_type.value == value)
                    or (key == "doc_id" and chunk.doc_id == value)
                    for key, value in where.items()
                )
                if ok:
                    filtered[chunk.id] = chunk
            return filtered

        return {chunk.id: chunk for chunk in chunks}


def build_context_block(chunks: list[RetrievedChunk]) -> tuple[str, list[SourceRef]]:
    """把检索结果拼成带 [S1]…[Sn] 标记的上下文。

    标记法是引用可核验的关键：模型必须在结论后标注 [Sn]，
    解析时把 Sn 映射回真实 chunk_id 写入 citation 表。
    模型若引用了不存在的编号，一眼可辨。
    """
    lines: list[str] = []
    sources: list[SourceRef] = []
    for index, chunk in enumerate(chunks, start=1):
        marker = f"S{index}"
        location = " · ".join(
            part
            for part in (chunk.source_name, chunk.section, f"第{chunk.page}页" if chunk.page else None)
            if part
        )
        lines.append(f"[{marker}] （{location}）\n{chunk.text}")
        sources.append(chunk.to_source_ref(marker=marker))
    return "\n\n".join(lines), sources
