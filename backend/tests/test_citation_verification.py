"""Citation / Verification Layer 的证据真实性测试。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import EvidenceSufficiency, EvidenceType, SourceType
from app.models.job_market import JobPosting
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.models.ontology import Job
from app.schemas.common import SourceRef
from app.services.citation_verification_service import CitationVerificationService


def _seed_evidence(db: Session) -> None:
    db.add(Job(id="job_a", name="测试岗位"))
    db.flush()
    db.add(
        KnowledgeDoc(
            id="doc_a",
            title="测试规范",
            source_name="《测试规范》",
            source_type=SourceType.INDUSTRY_SPEC,
            standard_id="TEST-001",
        )
    )
    db.add(
        KnowledgeChunk(
            id="doc_a#0",
            doc_id="doc_a",
            chunk_index=0,
            text="数据标注应保留可核验的质量检查记录。",
            page="12",
            section="质量控制",
        )
    )
    db.add(
        JobPosting(
            id="posting_a",
            job_id="job_a",
            title="数据标注工程师",
            source_name="公开招聘平台",
            source_url="https://example.test/posting-a",
            raw_text="负责图像数据标注、质量检查和交付记录。",
        )
    )
    db.commit()


def test_documentary_source_is_canonicalised_and_invalid_anchor_is_excluded(
    db: Session,
) -> None:
    _seed_evidence(db)
    result = CitationVerificationService(db).verify_sources(
        [
            SourceRef(
                type=EvidenceType.DOCUMENTARY,
                marker="S1",
                chunk_id="doc_a#0",
                source_name="伪造来源名",
                quote="伪造引文",
            ),
            SourceRef(
                type=EvidenceType.DOCUMENTARY,
                marker="S2",
                chunk_id="missing#0",
            ),
        ]
    )

    assert result.evidence_sufficiency is EvidenceSufficiency.PARTIAL
    assert len(result.sources) == 1
    source = result.sources[0]
    assert source.verified is True
    assert source.source_name == "《测试规范》"
    assert source.quote == "数据标注应保留可核验的质量检查记录。"
    assert any("missing#0" in warning for warning in result.warnings)


def test_statistical_source_is_anchored_to_original_posting(db: Session) -> None:
    _seed_evidence(db)
    result = CitationVerificationService(db).verify_sources(
        [SourceRef(type=EvidenceType.STATISTICAL, marker="S1", posting_id="posting_a")]
    )

    assert result.evidence_sufficiency is EvidenceSufficiency.SUFFICIENT
    source = result.sources[0]
    assert source.source_type is SourceType.JOB_POSTING
    assert source.url == "https://example.test/posting-a"
    assert source.quote == "负责图像数据标注、质量检查和交付记录。"
