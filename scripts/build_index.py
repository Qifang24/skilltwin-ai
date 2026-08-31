"""为知识库构建检索索引（向量 + BM25）。

    python scripts/build_index.py              # 增量：只嵌入尚未索引的块
    python scripts/build_index.py --rebuild    # 清空重建

首次运行会下载 embedding 模型（BAAI/bge-small-zh-v1.5，约 95MB）。
有 CUDA 时自动用 GPU。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.db import create_all, session_scope  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.knowledge import KnowledgeChunk  # noqa: E402
from app.rag.bm25 import BM25Index  # noqa: E402
from app.rag.embeddings import get_embedding_provider  # noqa: E402
from app.rag.retriever import BM25_INDEX_PATH  # noqa: E402
from app.rag.vector_store import build_vector_store  # noqa: E402

BATCH = 64


def main() -> int:
    parser = argparse.ArgumentParser(description="构建知识库检索索引")
    parser.add_argument("--rebuild", action="store_true", help="清空后重建")
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging("WARNING")
    create_all()

    embedder = get_embedding_provider()
    store = build_vector_store()

    print(f"Embedding : {settings.embedding_model} ({embedder.name})")
    print(f"向量库    : {settings.chroma_dir}")

    if args.rebuild:
        store.reset()
        print("已清空向量库")

    with session_scope() as db:
        chunks = db.query(KnowledgeChunk).order_by(KnowledgeChunk.id).all()
        if not chunks:
            print("❌ 知识库为空，请先运行 scripts/ingest_knowledge.py")
            return 1

        indexed = store.count()
        print(f"知识块    : {len(chunks)}（向量库现有 {indexed}）\n")

        # ---------- 向量索引 ----------
        pending = (
            chunks
            if args.rebuild or indexed == 0
            else [c for c in chunks if c.embedding_model != settings.embedding_model]
        )

        if pending:
            print(f"待嵌入 {len(pending)} 块，分 {(len(pending) + BATCH - 1) // BATCH} 批：")
            started = time.perf_counter()
            for offset in range(0, len(pending), BATCH):
                batch = pending[offset : offset + BATCH]
                vectors = embedder.embed([c.text for c in batch])
                store.upsert(
                    ids=[c.id for c in batch],
                    vectors=vectors,
                    metadatas=[
                        {
                            "doc_id": c.doc_id,
                            "page": c.page,
                            "section": c.section,
                            "source_type": c.doc.source_type.value if c.doc else None,
                            "job": c.doc.job if c.doc else None,
                            "skill_codes": list(c.skill_codes or []),
                        }
                        for c in batch
                    ],
                    documents=[c.text for c in batch],
                )
                for chunk in batch:
                    chunk.embedding_model = settings.embedding_model
                    chunk.vector_id = chunk.id
                print(f"   {min(offset + BATCH, len(pending)):4d}/{len(pending)}")
            elapsed = time.perf_counter() - started
            print(
                f"向量索引完成：{len(pending)} 块，耗时 {elapsed:.1f}s"
                f"（{len(pending) / max(elapsed, 0.001):.1f} 块/秒）\n"
            )
        else:
            print("向量索引已是最新，跳过\n")

        # ---------- BM25 索引 ----------
        # BM25 构建很快，每次全量重建，避免增量带来的不一致
        bm25 = BM25Index()
        bm25.build([c.id for c in chunks], [c.text for c in chunks])
        bm25.save(BM25_INDEX_PATH)
        print(f"BM25 索引完成：{bm25.size} 块 → {BM25_INDEX_PATH.name}")

    print(f"\n向量库现有 {store.count()} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
