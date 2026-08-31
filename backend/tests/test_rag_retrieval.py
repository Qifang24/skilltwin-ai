"""检索链路测试。

用 HashEmbeddingProvider + NumpyVectorStore，不加载真实模型：
测试要快、要离线、要确定性。真实模型的效果由
scripts/eval_retrieval.py 用评测集衡量，那是另一回事。
"""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.core.enums import SourceType
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.rag.bm25 import BM25Index, tokenize
from app.rag.embeddings import HashEmbeddingProvider, l2_normalize
from app.rag.retriever import (
    HybridRetriever,
    build_context_block,
    reciprocal_rank_fusion,
)
from app.rag.vector_store import NumpyVectorStore

DOCS = [
    ("c1", "能根据标注规范和要求, 完成文本、视觉、语音数据清洗"),
    ("c2", "计算机视觉实训室设备要求见表7, 需配备图像标注工作站"),
    ("c3", "标注工具 Label Studio 支持图像分类与目标检测标注"),
    ("c4", "职业道德要求诚实公正、严谨求是、遵纪守法"),
]


@pytest.fixture
def corpus(db: Session) -> Session:
    doc = KnowledgeDoc(
        id="d1",
        title="测试文档",
        source_name="《测试标准》",
        source_type=SourceType.NATIONAL_STANDARD,
        standard_id="TEST-1",
    )
    db.add(doc)
    for index, (chunk_id, text) in enumerate(DOCS):
        db.add(
            KnowledgeChunk(
                id=chunk_id,
                doc_id="d1",
                chunk_index=index,
                text=text,
                page=str(index + 1),
                section=f"{index + 1} 测试章节",
            )
        )
    db.commit()
    return db


def _retriever() -> HybridRetriever:
    embedder = HashEmbeddingProvider(dim=128)
    store = NumpyVectorStore()
    ids = [c[0] for c in DOCS]
    texts = [c[1] for c in DOCS]
    store.upsert(ids, embedder.embed(texts), [{"doc_id": "d1"} for _ in ids])
    bm25 = BM25Index()
    bm25.build(ids, texts)
    return HybridRetriever(embedder, store, bm25)


# ---------------------------------------------------------------- 分词
def test_tokenize_keeps_technical_terms_intact() -> None:
    """`Label Studio` 若被切碎，BM25 就补不上 dense 对术语的漏召了。"""
    tokens = tokenize("使用 Label Studio 完成标注")
    assert "label" in tokens
    assert "studio" in tokens


def test_tokenize_preserves_versioned_terms() -> None:
    assert "yolov8" in tokenize("训练 YOLOv8 模型")


def test_tokenize_drops_stopwords() -> None:
    assert "的" not in tokenize("数据的标注")


# ---------------------------------------------------------------- 向量
def test_hash_embeddings_are_normalised() -> None:
    vectors = HashEmbeddingProvider(dim=64).embed(["数据标注", "计算机视觉"])
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_l2_normalize_handles_zero_vector() -> None:
    """零向量除零会产生 nan，污染整个索引。"""
    result = l2_normalize(np.zeros((1, 4), dtype=np.float32))
    assert not np.isnan(result).any()


def test_numpy_store_returns_ranked_hits() -> None:
    embedder = HashEmbeddingProvider(dim=128)
    store = NumpyVectorStore()
    ids = [c[0] for c in DOCS]
    store.upsert(ids, embedder.embed([c[1] for c in DOCS]), [{} for _ in ids])

    hits = store.search(embedder.embed_one("计算机视觉实训室"), top_k=2)
    assert len(hits) == 2
    assert hits[0].score >= hits[1].score


def test_numpy_store_filters_by_metadata() -> None:
    embedder = HashEmbeddingProvider(dim=64)
    store = NumpyVectorStore()
    store.upsert(
        ["a", "b"],
        embedder.embed(["文本一", "文本二"]),
        [{"doc_id": "x"}, {"doc_id": "y"}],
    )
    hits = store.search(embedder.embed_one("文本"), top_k=5, where={"doc_id": "y"})
    assert [h.chunk_id for h in hits] == ["b"]


# ---------------------------------------------------------------- BM25
def test_bm25_finds_exact_term() -> None:
    index = BM25Index()
    index.build([c[0] for c in DOCS], [c[1] for c in DOCS])
    hits = index.search("Label Studio", top_k=3)
    assert hits and hits[0].chunk_id == "c3"


def test_bm25_returns_empty_for_unrelated_query() -> None:
    """一个词都没命中就该返回空，而不是硬凑几条出来。"""
    index = BM25Index()
    index.build([c[0] for c in DOCS], [c[1] for c in DOCS])
    assert index.search("量子纠缠超导材料", top_k=3) == []


def test_bm25_empty_index_is_safe() -> None:
    assert BM25Index().search("任意查询", top_k=3) == []


# ---------------------------------------------------------------- RRF
def test_rrf_rewards_agreement_between_paths() -> None:
    """两路都靠前的条目应排到只有一路召回的前面。"""
    scores = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert scores["b"] > scores["c"]
    assert scores["a"] > scores["d"]


def test_rrf_is_scale_free() -> None:
    """RRF 只用排名不用分数，因此与各通路的分数量纲无关。"""
    scores = reciprocal_rank_fusion([["x"]], k=60)
    assert scores["x"] == pytest.approx(1 / 61)


# ---------------------------------------------------------------- 混合检索
def test_hybrid_search_returns_relevant_chunk(corpus: Session) -> None:
    results = _retriever().search(corpus, "Label Studio 标注工具", top_n=3)
    assert results
    assert "c3" in [r.chunk_id for r in results]


def test_results_carry_citation_metadata(corpus: Session) -> None:
    """检索结果必须带齐出处，否则引用无从生成。"""
    result = _retriever().search(corpus, "数据清洗", top_n=1)[0]
    assert result.source_name == "《测试标准》"
    assert result.standard_id == "TEST-1"
    assert result.page is not None


def test_disabling_dense_path_uses_bm25_only(corpus: Session) -> None:
    """k=0 必须真的关闭该通路。

    回归：早期用 `k or 默认值`，传 0 会回落成默认值，
    导致「单路 vs 混合」的对比实际跑的是同一套，评测结论全是假的。
    """
    results = _retriever().search(corpus, "Label Studio", top_n=3, dense_k=0)
    assert results
    assert all(r.dense_rank is None for r in results)
    assert all(r.sparse_rank is not None for r in results)


def test_disabling_sparse_path_uses_dense_only(corpus: Session) -> None:
    results = _retriever().search(corpus, "数据清洗", top_n=3, sparse_k=0)
    assert results
    assert all(r.sparse_rank is None for r in results)


def test_empty_query_returns_nothing(corpus: Session) -> None:
    assert _retriever().search(corpus, "   ") == []


# ---------------------------------------------------------------- 上下文拼装
def test_context_block_has_numbered_markers(corpus: Session) -> None:
    """[Sn] 标记法是引用可核验的基础：模型引用了不存在的编号，一眼可辨。"""
    chunks = _retriever().search(corpus, "数据清洗 标注", top_n=2)
    block, sources = build_context_block(chunks)

    assert "[S1]" in block
    assert len(sources) == len(chunks)
    assert sources[0].marker == "S1"
    assert sources[0].chunk_id == chunks[0].chunk_id
    # 出自真实入库 chunk，非模型生成
    assert sources[0].verified is True


def test_context_block_includes_page_location(corpus: Session) -> None:
    block, _ = build_context_block(_retriever().search(corpus, "数据清洗", top_n=1))
    assert "《测试标准》" in block
    assert "第" in block and "页" in block
