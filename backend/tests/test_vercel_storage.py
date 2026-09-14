"""Serverless storage keeps vectors and uploaded source files across sessions."""

from __future__ import annotations

import json

import numpy as np
from sqlalchemy.orm import Session

from app.api.v1.knowledge import SearchRequest, search
from app.core.config import Settings, settings
from app.core.enums import SourceType
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.rag.embeddings import AI_GATEWAY_URL, OpenAICompatEmbeddingProvider
from app.rag.vector_store import SQLVectorStore
from app.services.curriculum_management_service import CurriculumManagementService


def test_blank_vercel_environment_values_use_defaults(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "")
    monkeypatch.setenv("DEMO_MODE", "")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "")
    monkeypatch.setenv("RETRIEVE_SPARSE_TOP_K", "")

    configured = Settings(_env_file=None)

    assert configured.debug is False
    assert configured.demo_mode.value == "live"
    assert configured.llm_timeout_seconds == 120.0
    assert configured.retrieve_sparse_top_k == 20


def test_ai_gateway_uses_oidc_instead_of_external_llm_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_api_key", "")
    monkeypatch.setattr(settings, "ai_gateway_api_key", "")
    monkeypatch.setattr(settings, "llm_api_key", "external-provider-key")
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "vercel-token")

    provider = OpenAICompatEmbeddingProvider(base_url=AI_GATEWAY_URL)
    assert provider._api_key == "vercel-token"


def test_sql_vector_store_survives_new_store_instances(db: Session) -> None:
    db.add(KnowledgeDoc(id="doc", title="Verified", source_name="Verified source", source_type=SourceType.NATIONAL_STANDARD))
    db.flush()
    db.add_all([
        KnowledgeChunk(id="a", doc_id="doc", chunk_index=0, text="标注规范", extra={"page_span": [1]}),
        KnowledgeChunk(id="b", doc_id="doc", chunk_index=1, text="模型训练"),
    ])
    db.commit()

    SQLVectorStore().upsert(
        ["a", "b"], np.asarray([[1, 0], [0, 1]], dtype=np.float32),
        [{"doc_id": "doc", "job": "annotation"}, {"doc_id": "doc", "job": "training"}],
    )

    reopened = SQLVectorStore()
    assert reopened.count() == 2
    assert [hit.chunk_id for hit in reopened.search(np.asarray([1, 0], dtype=np.float32), 2)] == ["a", "b"]
    assert [hit.chunk_id for hit in reopened.search(np.asarray([1, 0], dtype=np.float32), 2, where={"job": "training"})] == ["b"]
    db.expire_all()
    assert db.get(KnowledgeChunk, "a").extra["page_span"] == [1]
    reopened.reset()
    assert SQLVectorStore().count() == 0


def test_keyword_only_search_counts_postgres_chunks(db: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "vector_store", "sql")
    monkeypatch.setattr(settings, "retrieve_dense_top_k", 0)
    db.add(KnowledgeDoc(id="doc", title="Verified", source_name="Verified source", source_type=SourceType.NATIONAL_STANDARD))
    db.flush()
    db.add_all([
        KnowledgeChunk(id="a", doc_id="doc", chunk_index=0, text="数据标注规范"),
        KnowledgeChunk(id="b", doc_id="doc", chunk_index=1, text="机器视觉采集"),
        KnowledgeChunk(id="c", doc_id="doc", chunk_index=2, text="课程设计过程"),
    ])
    db.commit()

    result = search(SearchRequest(query="数据标注"), db)

    assert result.total_indexed == 3
    assert len(result.hits) == 1
    assert result.hits[0].sparse_rank == 1
    assert result.hits[0].dense_rank is None


def test_curriculum_import_source_survives_new_session(db: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "file_storage", "database")
    payload = json.dumps({"courses": [{"name": "数据标注", "description": "数据标注实训"}]}).encode()
    service = CurriculumManagementService(db)
    batch = service.create_import(
        filename="courses.json", content=payload, source_name="Verified source",
        source_url=None, license_note=None,
    )
    db.commit()
    batch_id = batch.id
    db.expire_all()

    restored = CurriculumManagementService(db)
    stored = restored.get_import(batch_id)
    assert stored.storage_path == ""
    assert stored.file_content == payload
    restored.parse_import(stored)
    plan = restored.confirm_import(batch_id, plan_id="plan", name="Plan", profession=None, version=None, is_partial=True)
    db.commit()
    assert plan.id == "plan"
