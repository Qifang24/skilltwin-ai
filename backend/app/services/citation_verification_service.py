"""证据引用的核验与审计落盘。

模型永远不能自行声明引用已验证：它只能引用服务端给出的 ``[S1]`` 标记。
本服务会把标记还原为数据库中的真实文献片段或岗位原文，再把已核验的
引用写入 ``citation`` 审计表。找不到锚点的引用不会返回给前端，也不会
被计入置信度。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.enums import EvidenceSufficiency, EvidenceType, SourceType
from app.models.audit import Citation
from app.models.job_market import JobPosting
from app.models.knowledge import KnowledgeChunk
from app.schemas.common import SourceRef


@dataclass(frozen=True)
class CitationClaim:
    """一条面向用户的结论及其允许使用的证据标记。"""

    text: str
    markers: tuple[str, ...] = ()


@dataclass
class VerificationResult:
    sources: list[SourceRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.INSUFFICIENT
    confidence: float = 0.35


class CitationVerificationService:
    """将临时 ``SourceRef`` 规范化为真实、可回查的证据。"""

    def __init__(self, db: Session) -> None:
        self._db = db

    def verify_sources(self, sources: Iterable[SourceRef]) -> VerificationResult:
        verified: list[SourceRef] = []
        warnings: list[str] = []
        seen: set[tuple[EvidenceType, str]] = set()
        submitted = list(sources)

        for source in submitted:
            canonical = self._canonical_source(source, warnings)
            if canonical is None:
                continue
            evidence_id = canonical.chunk_id or canonical.posting_id
            assert evidence_id is not None  # _canonical_source 已保证锚点存在
            key = (canonical.type, evidence_id)
            if key not in seen:
                verified.append(canonical)
                seen.add(key)

        if not verified:
            warnings.append("当前知识库暂无足够依据，相关结论未通过来源核验")
            return VerificationResult(sources=[], warnings=warnings)

        sufficiency = (
            EvidenceSufficiency.PARTIAL
            if len(verified) < len(submitted)
            else EvidenceSufficiency.SUFFICIENT
        )
        if sufficiency is EvidenceSufficiency.PARTIAL:
            warnings.append("部分引用无法定位到原始证据，已从结果中排除")

        # 置信度只表达“可回查证据的充分程度”，不代表模型事实必然正确。
        evidence_confidence = min(0.95, 0.55 + 0.15 * len(verified))
        if sufficiency is EvidenceSufficiency.PARTIAL:
            evidence_confidence *= 0.8
        return VerificationResult(
            sources=verified,
            warnings=warnings,
            evidence_sufficiency=sufficiency,
            confidence=round(evidence_confidence, 3),
        )

    def verify_and_record(
        self,
        *,
        llm_run_id: str,
        sources: Iterable[SourceRef],
        claims: Iterable[CitationClaim],
    ) -> VerificationResult:
        """核验来源并按“结论 → 证据”粒度写入审计记录。"""
        result = self.verify_sources(sources)
        by_marker = {source.marker: source for source in result.sources if source.marker}

        for claim in claims:
            claim_sources = (
                [by_marker[marker] for marker in claim.markers if marker in by_marker]
                if claim.markers
                else result.sources
            )
            for source in claim_sources:
                self._db.add(
                    Citation(
                        llm_run_id=llm_run_id,
                        claim=claim.text[:1000],
                        marker=source.marker,
                        evidence_type=source.type,
                        chunk_id=source.chunk_id,
                        posting_id=source.posting_id,
                        quote=source.quote,
                        relevance=source.relevance,
                        verified=True,
                        verifier_note=self._verifier_note(source),
                    )
                )
        self._db.flush()
        return result

    def _canonical_source(
        self, source: SourceRef, warnings: list[str]
    ) -> SourceRef | None:
        if source.type is EvidenceType.DOCUMENTARY:
            if not source.chunk_id:
                warnings.append("文献引用缺少 chunk_id，无法核验，已排除")
                return None
            chunk = self._db.get(KnowledgeChunk, source.chunk_id)
            if chunk is None or chunk.doc is None:
                warnings.append(f"文献引用 {source.chunk_id} 不存在，已排除")
                return None
            doc = chunk.doc
            return SourceRef(
                type=EvidenceType.DOCUMENTARY,
                marker=source.marker,
                chunk_id=chunk.id,
                source_name=doc.source_name,
                source_type=doc.source_type,
                standard_id=doc.standard_id,
                page=chunk.page,
                section=chunk.section,
                url=doc.source_url,
                quote=chunk.text[:300],
                relevance=source.relevance,
                verified=True,
            )

        if source.type is EvidenceType.STATISTICAL:
            if not source.posting_id:
                warnings.append("岗位统计引用缺少 posting_id，无法核验，已排除")
                return None
            posting = self._db.get(JobPosting, source.posting_id)
            if posting is None:
                warnings.append(f"岗位统计引用 {source.posting_id} 不存在，已排除")
                return None
            return SourceRef(
                type=EvidenceType.STATISTICAL,
                marker=source.marker,
                posting_id=posting.id,
                source_name=posting.source_name or posting.title,
                source_type=SourceType.JOB_POSTING,
                url=posting.source_url,
                quote=posting.raw_text[:300],
                relevance=source.relevance,
                verified=True,
            )

        warnings.append(f"不支持的证据类型 {source.type}，已排除")
        return None

    @staticmethod
    def _verifier_note(source: SourceRef) -> str:
        anchor = source.chunk_id or source.posting_id
        return f"已核验锚点 {anchor} 存在，展示元数据与引文均由服务端回填"
