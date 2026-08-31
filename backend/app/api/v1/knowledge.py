"""知识库检索接口。

`/search` 既是给 Agent 用的能力，也是排查「为什么召回了这条 / 为什么没召回」
的工具 —— 返回里带 dense_rank / sparse_rank，能看出是哪条通路把它捞上来的。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.enums import SourceType
from app.core.errors import NotFoundError
from app.models.knowledge import KnowledgeDoc
from app.rag.retriever import HybridRetriever
from app.schemas.common import Page

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_n: int = Field(default=8, ge=1, le=30)
    #: 限定来源类型，例如只查国家标准
    source_type: SourceType | None = None
    doc_id: str | None = None


class SearchHit(BaseModel):
    chunk_id: str
    text: str
    score: float
    #: 各通路的排名，None 表示该通路未召回此条
    dense_rank: int | None = None
    sparse_rank: int | None = None
    doc_id: str | None = None
    source_name: str | None = None
    standard_id: str | None = None
    source_type: str | None = None
    page: str | None = None
    section: str | None = None
    citation: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    total_indexed: int


class DocRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source_name: str
    source_type: SourceType
    standard_id: str | None = None
    publisher: str | None = None
    pub_year: int | None = None
    source_url: str | None = None
    license_note: str | None = None
    chunk_count: int = 0


def _citation_label(hit) -> str:  # noqa: ANN001
    parts = [
        part
        for part in (
            hit.source_name,
            hit.standard_id,
            hit.section,
            f"第{hit.page}页" if hit.page else None,
        )
        if part
    ]
    return " · ".join(parts)


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="知识库混合检索",
    description=(
        "dense（本地 BGE 向量）+ BM25（jieba 分词）双通路，经 RRF 融合。"
        "返回中的 dense_rank / sparse_rank 可用于排查召回来源。"
    ),
)
def search(payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    retriever = HybridRetriever()

    where: dict = {}
    if payload.source_type:
        where["source_type"] = payload.source_type.value
    if payload.doc_id:
        where["doc_id"] = payload.doc_id

    chunks = retriever.search(db, payload.query, top_n=payload.top_n, where=where or None)

    return SearchResponse(
        query=payload.query,
        hits=[
            SearchHit(
                chunk_id=c.chunk_id,
                text=c.text,
                score=c.score,
                dense_rank=c.dense_rank,
                sparse_rank=c.sparse_rank,
                doc_id=c.doc_id,
                source_name=c.source_name,
                standard_id=c.standard_id,
                source_type=c.source_type,
                page=c.page,
                section=c.section,
                citation=_citation_label(c),
            )
            for c in chunks
        ],
        total_indexed=retriever.store.count(),
    )


@router.get(
    "/docs",
    response_model=Page[DocRead],
    summary="知识库文档列表",
    description="含来源与许可说明，用于核验知识库的每一份资料出处。",
)
def list_docs(
    db: Session = Depends(get_db),
    source_type: SourceType | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[DocRead]:
    filters = []
    if source_type:
        filters.append(KnowledgeDoc.source_type == source_type)

    total = db.execute(
        select(func.count()).select_from(KnowledgeDoc).where(*filters)
    ).scalar_one()
    docs = (
        db.execute(
            select(KnowledgeDoc)
            .where(*filters)
            .order_by(KnowledgeDoc.source_type, KnowledgeDoc.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    items = []
    for doc in docs:
        item = DocRead.model_validate(doc)
        item.chunk_count = len(doc.chunks)
        items.append(item)

    return Page[DocRead](items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/docs/{doc_id}",
    response_model=DocRead,
    summary="文档详情",
)
def get_doc(doc_id: str, db: Session = Depends(get_db)) -> DocRead:
    doc = db.get(KnowledgeDoc, doc_id)
    if doc is None:
        raise NotFoundError(f"未找到文档：{doc_id}", detail={"doc_id": doc_id})
    item = DocRead.model_validate(doc)
    item.chunk_count = len(doc.chunks)
    return item
