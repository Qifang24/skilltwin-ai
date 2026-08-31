"""BaseAgent 的结构校验与自我修复测试。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.core.config import DemoMode
from app.core.enums import EvidenceSufficiency, EvidenceType, LLMRunStatus, SourceType
from app.core.errors import LLMOutputParseError
from app.core.llm import EchoProvider, Message
from app.core.llm_runner import LLMRunner
from app.models.audit import Citation, LLMRun
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.schemas.common import SourceRef


class SkillList(BaseModel):
    job: str
    skills: list[str] = Field(min_length=1)


class DemoAgent(BaseAgent[str, SkillList]):
    name = "demo_agent"
    output_model = SkillList

    def render_prompt(self, inp: str, sources: list[SourceRef]) -> list[Message]:
        return [Message(role="user", content=f"列出 {inp} 的技能")]


class SourcedAgent(DemoAgent):
    """带检索依据的 Agent，用于验证「有依据」与「无依据」两条分支。"""

    name = "sourced_agent"

    def retrieve(self, db: Session, inp: str) -> list[SourceRef]:
        return [
            SourceRef(
                type=EvidenceType.DOCUMENTARY,
                marker="S1",
                chunk_id="doc_x#0",
                source_name="《数据标注作业规范》",
                quote="矩形框应紧贴目标物体外接边缘",
                verified=True,
            )
        ]


def _agent(cls: type[DemoAgent], scripted: list[str]) -> DemoAgent:
    return cls(
        runner=LLMRunner(provider=EchoProvider(scripted), demo_mode=DemoMode.LIVE)
    )


# ---------------------------------------------------------------- 正常路径


def test_valid_output_produces_envelope(db: Session) -> None:
    agent = _agent(DemoAgent, ['{"job": "标注工程师", "skills": ["python", "cvat"]}'])
    envelope = agent.run(db, "AI数据标注工程师")

    assert envelope.result.job == "标注工程师"
    assert envelope.result.skills == ["python", "cvat"]
    assert envelope.ai_generated is True
    assert envelope.confidence == 0.315
    assert envelope.llm_run_id is not None


def test_output_is_written_back_to_llm_run(db: Session) -> None:
    agent = _agent(DemoAgent, ['{"job": "j", "skills": ["a"]}'])
    envelope = agent.run(db, "x")

    run = db.get(LLMRun, envelope.llm_run_id)
    assert run is not None
    assert run.output_json == {"job": "j", "skills": ["a"]}
    assert run.repair_attempts == 0
    assert run.status is LLMRunStatus.SUCCESS


def test_markdown_fenced_output_is_accepted(db: Session) -> None:
    agent = _agent(DemoAgent, ['```json\n{"job": "j", "skills": ["a"]}\n```'])
    assert agent.run(db, "x").result.skills == ["a"]


# ---------------------------------------------------------------- 证据分支


def test_no_sources_is_marked_insufficient(db: Session) -> None:
    """没有检索依据时必须诚实标注，而不是默认「充分」。"""
    agent = _agent(DemoAgent, ['{"job": "j", "skills": ["a"]}'])
    envelope = agent.run(db, "x")

    assert envelope.sources == []
    assert envelope.evidence_sufficiency is EvidenceSufficiency.INSUFFICIENT
    assert any("暂无足够依据" in w for w in envelope.warnings)


def test_with_sources_is_marked_sufficient(db: Session) -> None:
    db.add(
        KnowledgeDoc(
            id="doc_x",
            title="测试标准",
            source_name="《数据标注作业规范》",
            source_type=SourceType.INDUSTRY_SPEC,
        )
    )
    db.add(
        KnowledgeChunk(
            id="doc_x#0",
            doc_id="doc_x",
            chunk_index=0,
            text="矩形框应紧贴目标物体外接边缘。",
        )
    )
    db.commit()
    agent = _agent(SourcedAgent, ['{"job": "j", "skills": ["a"]}'])
    envelope = agent.run(db, "x")

    assert len(envelope.sources) == 1
    assert envelope.sources[0].chunk_id == "doc_x#0"
    assert envelope.evidence_sufficiency is EvidenceSufficiency.SUFFICIENT
    assert not any("暂无足够依据" in w for w in envelope.warnings)
    citation = db.query(Citation).filter_by(llm_run_id=envelope.llm_run_id).one()
    assert citation.chunk_id == "doc_x#0" and citation.verified is True


# ---------------------------------------------------------------- 修复路径


def test_invalid_output_triggers_repair_and_succeeds(db: Session) -> None:
    """首次缺字段，模型按报错修正后通过。"""
    agent = _agent(
        DemoAgent,
        [
            '{"job": "只有这一个字段"}',                       # 缺 skills
            '{"job": "标注工程师", "skills": ["python"]}',      # 修复后
        ],
    )
    envelope = agent.run(db, "x")

    assert envelope.result.skills == ["python"]
    assert envelope.confidence == 0.245  # 修复过且无可核验来源，置信度下调
    assert any("修正后通过" in w for w in envelope.warnings)


def test_repair_prompt_contains_validation_errors(db: Session) -> None:
    """修复提示必须把具体报错喂回模型，否则它只能瞎猜。"""
    provider = EchoProvider(
        ['{"job": "x"}', '{"job": "x", "skills": ["a"]}']
    )
    agent = DemoAgent(runner=LLMRunner(provider=provider, demo_mode=DemoMode.LIVE))
    agent.run(db, "x")

    repair_conversation = provider.calls[1]
    repair_text = repair_conversation[-1].content
    assert "skills" in repair_text
    assert repair_conversation[-2].role == "assistant"


def test_unrepairable_output_raises_and_marks_run(db: Session) -> None:
    """修不好就明确报错，绝不返回半成品。"""
    agent = _agent(DemoAgent, ["这不是 JSON", "这还不是 JSON"])

    with pytest.raises(LLMOutputParseError) as exc_info:
        agent.run(db, "x")

    assert exc_info.value.detail["agent"] == "demo_agent"
    failed_run = db.get(LLMRun, exc_info.value.detail["llm_run_id"])
    assert failed_run is not None
    assert failed_run.status is LLMRunStatus.PARSE_FAILED


def test_cache_hit_is_surfaced_in_warnings(db: Session) -> None:
    """回放出来的结果要让用户知道，不能伪装成实时生成。"""
    runner = LLMRunner(
        provider=EchoProvider(['{"job": "j", "skills": ["a"]}']),
        demo_mode=DemoMode.RECORD,
    )
    agent = DemoAgent(runner=runner)

    agent.run(db, "x")
    second = agent.run(db, "x")

    assert any("缓存回放" in w for w in second.warnings)
