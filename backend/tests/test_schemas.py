"""Agent 响应信封契约测试。

信封是全系统「可解释性」的 API 层落点：任何专业结论都必须能回答
「依据是什么、有多确信、够不够」三个问题。
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.core.enums import EvidenceSufficiency, EvidenceType, SourceType
from app.schemas.common import AgentEnvelope, Page, SourceRef


class _Demo(BaseModel):
    skills: list[str]


def test_envelope_defaults_are_conservative() -> None:
    """默认必须是「AI 生成、无证据、零置信」——乐观值必须显式给出。"""
    env = AgentEnvelope[_Demo](result=_Demo(skills=["python"]))
    assert env.ai_generated is True
    assert env.confidence == 0.0
    assert env.sources == []
    assert env.has_evidence is False
    assert env.evidence_sufficiency is EvidenceSufficiency.PARTIAL


def test_envelope_carries_typed_result_and_sources() -> None:
    env = AgentEnvelope[_Demo](
        result=_Demo(skills=["python", "label_studio"]),
        reasoning_summary="基于 3 条行业规范条目归纳",
        sources=[
            SourceRef(
                type=EvidenceType.DOCUMENTARY,
                marker="S1",
                chunk_id="doc_x#0",
                source_name="《数据标注作业规范》",
                source_type=SourceType.INDUSTRY_SPEC,
                page="12",
                quote="矩形框应紧贴目标物体外接边缘",
                verified=True,
            )
        ],
        confidence=0.82,
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        llm_run_id="run_001",
    )
    assert env.result.skills[1] == "label_studio"
    assert env.has_evidence is True
    assert "第12页" in env.sources[0].label()


def test_confidence_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentEnvelope[_Demo](result=_Demo(skills=[]), confidence=1.4)


def test_insufficient_evidence_is_representable() -> None:
    """「当前知识库暂无足够依据」必须是一等公民状态，而不是靠空字符串表达。"""
    env = AgentEnvelope[_Demo](
        result=_Demo(skills=[]),
        evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT,
        warnings=["当前知识库暂无足够依据"],
    )
    assert env.evidence_sufficiency is EvidenceSufficiency.INSUFFICIENT
    assert env.warnings == ["当前知识库暂无足够依据"]


def test_page_has_more() -> None:
    page = Page[str](items=["a", "b"], total=5, limit=2, offset=0)
    assert page.has_more is True
    assert Page[str](items=["e"], total=5, limit=2, offset=4).has_more is False
