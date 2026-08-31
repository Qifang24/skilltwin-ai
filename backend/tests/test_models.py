"""数据模型完整性测试。

重点验证「技能命名漂移 → 全系统 join 断裂」这条头号静默风险的防线：
skill_code 外键必须被数据库真正强制执行。
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core.enums import (
    EvidenceType,
    GraphStatus,
    LLMRunStatus,
    MasteryLevel,
    NodeType,
    SkillCategory,
    SourceType,
)
from app.models import (
    Citation,
    CompetencyGraph,
    CompetencyNode,
    Job,
    KnowledgeChunk,
    KnowledgeDoc,
    LLMRun,
    Skill,
)


def _seed_job_and_skill(db: Session) -> tuple[Job, Skill]:
    job = Job(id="ai_data_annotator", name="AI数据标注工程师", industry="人工智能")
    skill = Skill(
        skill_code="tool.label_studio",
        name_zh="Label Studio",
        category=SkillCategory.TOOL,
        aliases=["LabelStudio", "label-studio"],
    )
    db.add_all([job, skill])
    db.commit()
    return job, skill


def test_skill_aliases_mutation_is_persisted(db: Session) -> None:
    """MutableList：就地 append 也要能落库，否则别名会静默丢失。"""
    _, skill = _seed_job_and_skill(db)

    skill.aliases.append("标注工具Label Studio")
    db.commit()
    db.expire_all()

    reloaded = db.get(Skill, "tool.label_studio")
    assert reloaded is not None
    assert "标注工具Label Studio" in reloaded.aliases
    assert len(reloaded.aliases) == 3


def test_graph_node_hierarchy(db: Session) -> None:
    _seed_job_and_skill(db)

    graph = CompetencyGraph(
        id="g_ai_annot_v1", job_id="ai_data_annotator", version=1, title="AI数据标注工程师能力图谱"
    )
    parent = CompetencyNode(
        id="g1.cap.annotation",
        graph_id="g_ai_annot_v1",
        node_type=NodeType.COMPETENCY,
        name="数据标注能力",
        order_index=0,
    )
    child = CompetencyNode(
        id="g1.skill.label_studio",
        graph_id="g_ai_annot_v1",
        parent_id="g1.cap.annotation",
        node_type=NodeType.SKILL_POINT,
        name="Label Studio 使用",
        skill_code="tool.label_studio",
        mastery_level=MasteryLevel.APPLY,
        order_index=0,
    )
    db.add_all([graph, parent, child])
    db.commit()
    db.expire_all()

    loaded = db.get(CompetencyGraph, "g_ai_annot_v1")
    assert loaded is not None
    assert loaded.status is GraphStatus.DRAFT  # 默认必须是草案，不能直接可用
    assert len(loaded.nodes) == 2

    root = db.get(CompetencyNode, "g1.cap.annotation")
    assert root is not None
    assert [c.id for c in root.children] == ["g1.skill.label_studio"]
    assert root.children[0].parent is root


def test_node_with_unknown_skill_code_is_rejected(db: Session) -> None:
    """核心防线：技能外键必须由数据库强制，不能只靠应用层自觉。"""
    _seed_job_and_skill(db)
    db.add(CompetencyGraph(id="g2", job_id="ai_data_annotator", version=1))
    db.commit()

    db.add(
        CompetencyNode(
            id="g2.skill.typo",
            graph_id="g2",
            node_type=NodeType.SKILL_POINT,
            name="拼错的技能",
            skill_code="tool.labelstudio",  # 少了下划线，是个不存在的 code
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_graph_delete_cascades_to_nodes(db: Session) -> None:
    _seed_job_and_skill(db)
    db.add(CompetencyGraph(id="g3", job_id="ai_data_annotator", version=1))
    db.add(
        CompetencyNode(
            id="g3.cap.x", graph_id="g3", node_type=NodeType.COMPETENCY, name="能力X"
        )
    )
    db.commit()

    db.delete(db.get(CompetencyGraph, "g3"))
    db.commit()

    assert db.get(CompetencyNode, "g3.cap.x") is None


def test_graph_version_is_unique_per_job(db: Session) -> None:
    _seed_job_and_skill(db)
    db.add(CompetencyGraph(id="ga", job_id="ai_data_annotator", version=1))
    db.commit()

    db.add(CompetencyGraph(id="gb", job_id="ai_data_annotator", version=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_knowledge_chunk_citation_label(db: Session) -> None:
    doc = KnowledgeDoc(
        id="doc_gb_annot",
        title="数据标注作业规范",
        source_name="《数据标注作业规范》",
        source_type=SourceType.INDUSTRY_SPEC,
        standard_id="TEST-SPEC-001",
    )
    chunk = KnowledgeChunk(
        id="doc_gb_annot#0",
        doc_id="doc_gb_annot",
        chunk_index=0,
        text="矩形框应紧贴目标物体外接边缘……",
        page="12",
        section="4.2 目标检测标注",
        skill_codes=["annot.bbox"],
    )
    db.add_all([doc, chunk])
    db.commit()
    db.expire_all()

    loaded = db.get(KnowledgeChunk, "doc_gb_annot#0")
    assert loaded is not None
    label = loaded.citation_label()
    assert "《数据标注作业规范》" in label
    assert "TEST-SPEC-001" in label
    assert "第12页" in label


def test_llm_run_and_citation_roundtrip(db: Session) -> None:
    """审计链路：一次调用 → 若干条可核验引用。"""
    run = LLMRun(
        id="run_001",
        agent="competency_graph",
        provider="echo",
        model="test-model",
        prompt_hash="abc123",
        input_summary={"job_id": "ai_data_annotator"},
        output_json={"nodes": []},
        status=LLMRunStatus.SUCCESS,
    )
    run.citations.append(
        Citation(
            claim="目标检测标注需保证矩形框紧贴目标边缘",
            marker="S1",
            evidence_type=EvidenceType.DOCUMENTARY,
            quote="矩形框应紧贴目标物体外接边缘",
            verified=True,
        )
    )
    db.add(run)
    db.commit()
    db.expire_all()

    loaded = db.get(LLMRun, "run_001")
    assert loaded is not None
    assert loaded.cache_hit is False
    assert loaded.repair_attempts == 0
    assert len(loaded.citations) == 1
    assert loaded.citations[0].evidence_type is EvidenceType.DOCUMENTARY


def test_invalid_enum_value_is_rejected(db: Session) -> None:
    """非法枚举在类型处理层即被拦下，不会写进库形成脏取值。"""
    _seed_job_and_skill(db)
    db.add(CompetencyGraph(id="g4", job_id="ai_data_annotator", version=1))
    db.commit()

    db.add(
        CompetencyNode(
            id="g4.bad", graph_id="g4", node_type="not_a_real_type", name="非法类型"
        )
    )
    # IntegrityError 也是 StatementError 的子类，这里一并覆盖
    with pytest.raises(StatementError, match="not among the defined enum values"):
        db.commit()
    db.rollback()

    assert db.get(CompetencyNode, "g4.bad") is None
