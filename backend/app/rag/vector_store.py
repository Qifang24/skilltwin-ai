"""向量库抽象。

默认用 Chroma（本机已装，Windows 零构建风险）。
同时提供 numpy 暴力检索实现：知识库规模小于万级时性能完全够用，
且**零依赖**，让单元测试不必启动 Chroma 的持久化目录。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VectorHit:
    chunk_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    @abstractmethod
    def upsert(
        self,
        ids: list[str],
        vectors: np.ndarray,
        metadatas: list[dict[str, Any]],
        documents: list[str] | None = None,
    ) -> None: ...

    @abstractmethod
    def search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def reset(self) -> None: ...


class NumpyVectorStore(VectorStore):
    """内存暴力检索。向量已 L2 归一化，故内积即余弦相似度。"""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._matrix: np.ndarray | None = None
        self._metadatas: list[dict[str, Any]] = []

    def upsert(
        self,
        ids: list[str],
        vectors: np.ndarray,
        metadatas: list[dict[str, Any]],
        documents: list[str] | None = None,
    ) -> None:
        for index, chunk_id in enumerate(ids):
            vector = vectors[index]
            metadata = metadatas[index]
            if chunk_id in self._ids:
                position = self._ids.index(chunk_id)
                self._matrix[position] = vector  # type: ignore[index]
                self._metadatas[position] = metadata
                continue
            self._ids.append(chunk_id)
            self._metadatas.append(metadata)
            self._matrix = (
                vector.reshape(1, -1)
                if self._matrix is None
                else np.vstack([self._matrix, vector.reshape(1, -1)])
            )

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        if self._matrix is None or not self._ids:
            return []

        candidates = range(len(self._ids))
        if where:
            candidates = [
                i
                for i in candidates
                if all(self._metadatas[i].get(k) == v for k, v in where.items())
            ]
            if not candidates:
                return []

        indices = np.asarray(list(candidates))
        scores = self._matrix[indices] @ query_vector.reshape(-1)
        order = np.argsort(-scores)[:top_k]
        return [
            VectorHit(
                chunk_id=self._ids[indices[i]],
                score=float(scores[i]),
                metadata=self._metadatas[indices[i]],
            )
            for i in order
        ]

    def count(self) -> int:
        return len(self._ids)

    def reset(self) -> None:
        self._ids, self._matrix, self._metadatas = [], None, []


class ChromaVectorStore(VectorStore):
    """Chroma 持久化实现。"""

    def __init__(self, collection: str = "knowledge", path: str | None = None) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._path = path or str(settings.chroma_dir)
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self._path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection_name = collection
        # 余弦距离；我们的向量已归一化，与内积等价
        self._collection = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def upsert(
        self,
        ids: list[str],
        vectors: np.ndarray,
        metadatas: list[dict[str, Any]],
        documents: list[str] | None = None,
    ) -> None:
        if not ids:
            return
        self._collection.upsert(
            ids=ids,
            embeddings=[v.tolist() for v in vectors],
            metadatas=[_sanitise(m) for m in metadatas],
            documents=documents,
        )

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        if self.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[query_vector.reshape(-1).tolist()],
            n_results=min(top_k, self.count()),
            where=where or None,
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        # Chroma 返回余弦距离，转成相似度便于与其它通路统一比较
        return [
            VectorHit(chunk_id=cid, score=1.0 - float(dist), metadata=meta or {})
            for cid, dist, meta in zip(ids, distances, metadatas)
        ]

    def count(self) -> int:
        return int(self._collection.count())

    def reset(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name, metadata={"hnsw:space": "cosine"}
        )


class SQLVectorStore(VectorStore):
    """Small-corpus vector store persisted in the shared SQL database.

    The current corpus is a few hundred chunks, so scanning normalized vectors
    is fast enough and avoids a separate writable index on Vercel Functions.
    """

    def upsert(
        self,
        ids: list[str],
        vectors: np.ndarray,
        metadatas: list[dict[str, Any]],
        documents: list[str] | None = None,
    ) -> None:
        from app.core.db import session_scope
        from app.models.knowledge import KnowledgeChunk

        if len(ids) != len(vectors) or len(ids) != len(metadatas):
            raise ValueError("Vector IDs, embeddings and metadata must have the same length")
        with session_scope() as db:
            chunks = {
                chunk.id: chunk
                for chunk in db.execute(select(KnowledgeChunk).where(KnowledgeChunk.id.in_(ids))).scalars()
            }
            if len(chunks) != len(ids):
                raise ValueError("All vector IDs must refer to existing knowledge chunks")
            for chunk_id, vector, metadata in zip(ids, vectors, metadatas):
                chunk = chunks[chunk_id]
                chunk.extra = {
                    **(chunk.extra or {}),
                    "_embedding": vector.astype(float).tolist(),
                    "_vector_metadata": _sanitise(metadata),
                }
                chunk.vector_id = chunk_id

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        from app.core.db import session_scope
        from app.models.knowledge import KnowledgeChunk

        if top_k <= 0:
            return []
        with session_scope() as db:
            rows = db.execute(select(KnowledgeChunk.id, KnowledgeChunk.extra)).all()
        candidates: list[tuple[str, float, dict[str, Any]]] = []
        query = query_vector.reshape(-1)
        for chunk_id, extra in rows:
            vector = (extra or {}).get("_embedding")
            metadata = (extra or {}).get("_vector_metadata", {})
            if vector is None or (where and any(metadata.get(k) != v for k, v in where.items())):
                continue
            embedding = np.asarray(vector, dtype=np.float32)
            if embedding.shape != query.shape:
                continue
            candidates.append((chunk_id, float(embedding @ query), metadata))
        candidates.sort(key=lambda item: item[1], reverse=True)
        return [VectorHit(chunk_id=cid, score=score, metadata=meta) for cid, score, meta in candidates[:top_k]]

    def count(self) -> int:
        from app.core.db import session_scope
        from app.models.knowledge import KnowledgeChunk

        with session_scope() as db:
            extras = db.execute(select(KnowledgeChunk.extra)).scalars().all()
        return sum("_embedding" in (extra or {}) for extra in extras)

    def reset(self) -> None:
        from app.core.db import session_scope
        from app.models.knowledge import KnowledgeChunk

        with session_scope() as db:
            for chunk in db.execute(select(KnowledgeChunk)).scalars():
                chunk.extra = {k: v for k, v in (chunk.extra or {}).items() if k not in {"_embedding", "_vector_metadata"}}
                chunk.vector_id = None


def _sanitise(metadata: dict[str, Any]) -> dict[str, Any]:
    """Chroma 的 metadata 只接受标量。列表转成逗号分隔串，None 直接丢弃。"""
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if value:
                clean[key] = ",".join(str(v) for v in value)
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean


def build_vector_store(kind: str = "chroma") -> VectorStore:
    if kind == "chroma" and settings.vector_store == "sql":
        kind = "sql"
    if kind == "numpy":
        return NumpyVectorStore()
    if kind == "sql":
        return SQLVectorStore()
    return ChromaVectorStore()
