"""检索效果评测。

    python scripts/eval_retrieval.py              # 评测混合检索
    python scripts/eval_retrieval.py --compare    # 对比 dense / BM25 / 混合
    python scripts/eval_retrieval.py --verify     # 只核实评测集关键词是否真在语料中

没有评测集的 RAG 是不可信的：改了 chunk 大小、换了模型、调了融合参数，
无法说清到底变好还是变坏。--compare 尤其重要 —— 它用数据回答
「混合检索到底比单路强多少」，而不是靠直觉。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.db import session_scope  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.knowledge import KnowledgeChunk  # noqa: E402
from app.rag.bm25 import BM25Index  # noqa: E402
from app.rag.embeddings import get_embedding_provider  # noqa: E402
from app.rag.retriever import BM25_INDEX_PATH, HybridRetriever  # noqa: E402
from app.rag.vector_store import build_vector_store  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_FILE = PROJECT_ROOT / "data" / "eval" / "retrieval_eval.json"


def _expected_docs(case: dict) -> list[str]:
    """期望文档。有些问题本就有多个合理来源，不该武断地只认一个。"""
    if "expected_doc_ids" in case:
        return list(case["expected_doc_ids"])
    return [case["expected_doc_id"]]


def _is_relevant(chunk, case: dict) -> bool:
    """命中判定：来自期望文档之一 且 含期望关键词之一。

    两个条件缺一不可：只看文档会把同一文档里无关的块也算命中；
    只看关键词会把碰巧提到该词的其它文档算进来。
    """
    if chunk.doc_id not in _expected_docs(case):
        return False
    return any(kw in chunk.text for kw in case["expected_keywords"])


def _metrics(ranked_relevance: list[list[bool]], k: int = 5) -> dict[str, float]:
    """Recall@k 与 MRR。"""
    recall_hits = 0
    reciprocal_sum = 0.0
    for relevance in ranked_relevance:
        top_k = relevance[:k]
        if any(top_k):
            recall_hits += 1
        for rank, hit in enumerate(relevance, start=1):
            if hit:
                reciprocal_sum += 1.0 / rank
                break
    total = max(len(ranked_relevance), 1)
    return {
        f"recall@{k}": recall_hits / total,
        "mrr": reciprocal_sum / total,
    }


def _verify(cases: list[dict]) -> int:
    """核实评测集关键词确实存在于期望文档中 —— 评测集本身也不能凭印象写。"""
    problems = 0
    with session_scope() as db:
        chunks = db.query(KnowledgeChunk).all()
        for case in cases:
            expected = _expected_docs(case)
            doc_chunks = [c for c in chunks if c.doc_id in expected]
            if not doc_chunks:
                print(f"  ❌ {case['id']}：文档 {expected} 不存在")
                problems += 1
                continue
            found = [
                kw
                for kw in case["expected_keywords"]
                if any(kw in c.text for c in doc_chunks)
            ]
            if not found:
                print(
                    f"  ❌ {case['id']}：关键词 {case['expected_keywords']} "
                    f"在期望文档中均不存在，该题无法命中"
                )
                problems += 1
            else:
                print(f"  ✓ {case['id']}：{found}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="检索效果评测")
    parser.add_argument("--compare", action="store_true", help="对比三种检索策略")
    parser.add_argument("--verify", action="store_true", help="只核实评测集")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--show-misses", action="store_true", help="打印未命中的查询")
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging("ERROR")

    if not EVAL_FILE.exists():
        print(f"❌ 缺少评测集：{EVAL_FILE}")
        return 1
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))["queries"]

    if args.verify:
        print(f"核实评测集（{len(cases)} 题）：")
        problems = _verify(cases)
        print(f"\n{'✅ 全部可命中' if not problems else f'❌ {problems} 题有问题'}")
        return 1 if problems else 0

    embedder = get_embedding_provider()
    store = build_vector_store()
    bm25 = BM25Index.load(BM25_INDEX_PATH)
    retriever = HybridRetriever(embedder, store, bm25)

    print(f"评测集 {len(cases)} 题 | 语料 {store.count()} 块 | top_n={args.top_n}\n")

    strategies: dict[str, dict] = {}

    with session_scope() as db:
        chunk_cache = {c.id: c for c in db.query(KnowledgeChunk).all()}

        def run(name: str, dense_k: int, sparse_k: int) -> None:
            relevance_lists: list[list[bool]] = []
            misses: list[str] = []
            for case in cases:
                results = retriever.search(
                    db,
                    case["query"],
                    top_n=args.top_n,
                    dense_k=dense_k,
                    sparse_k=sparse_k,
                )
                relevance = [
                    _is_relevant(chunk_cache[r.chunk_id], case)
                    for r in results
                    if r.chunk_id in chunk_cache
                ]
                relevance_lists.append(relevance)
                if not any(relevance[: args.top_n]):
                    misses.append(f"{case['id']} 「{case['query']}」→ {case['note']}")
            strategies[name] = {
                **_metrics(relevance_lists, args.top_n),
                "misses": misses,
            }

        if args.compare:
            run("仅向量 (dense)", 20, 0)
            run("仅 BM25 (sparse)", 0, 20)
        run("混合 + RRF", 20, 20)

    width = max(len(n) for n in strategies)
    print(f"{'策略'.ljust(width)}   Recall@{args.top_n}    MRR")
    print("-" * (width + 22))
    for name, result in strategies.items():
        print(
            f"{name.ljust(width)}   {result[f'recall@{args.top_n}']:>7.1%}"
            f"   {result['mrr']:>6.3f}"
        )

    hybrid = strategies.get("混合 + RRF", {})
    if args.show_misses and hybrid.get("misses"):
        print(f"\n混合检索未命中的 {len(hybrid['misses'])} 题：")
        for miss in hybrid["misses"]:
            print(f"   • {miss}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
