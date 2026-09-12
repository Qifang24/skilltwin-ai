"""能力图谱生成、持久化与审核测试。

图谱是全系统数据中枢，这里守三条底线：
  ① 节点 ID 由服务端分配且稳定
  ② 技能点必须能 join 到技能表，否则丢弃
  ③ 只有 approved 图谱可被下游引用
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.enums import GraphStatus, NodeType, SkillCategory
from app.core.errors import ConflictError, ValidationError
from app.models.competency import CompetencyGraph, CompetencyNode
from app.models.ontology import Job, Skill
from app.schemas.common import SourceRef
from app.schemas.competency import CompetencyGraphDraft, NodeDraft
from app.services.competency_graph_service import CompetencyGraphService

SOURCES = [
    SourceRef(
        type="documentary",
        marker="S1",
        chunk_id="doc_std#10",
        source_name="《人工智能训练师国家职业技能标准（2021年版）》",
        page="6",
        section="3.1 五级/初级工",
        quote="能根据标注规范和要求, 完成文本、视觉、语音数据标注",
    )
]


@pytest.fixture
def seeded(db: Session) -> Session:
    db.add(Job(id="ai_data_annotator", name="AI数据标注工程师"))
    db.add_all(
        [
            Skill(skill_code="annot.image", name_zh="视觉数据标注", category=SkillCategory.ANNOTATION, aliases=["图像标注"]),
            Skill(skill_code="annot.text", name_zh="文本数据标注", category=SkillCategory.ANNOTATION),
            Skill(skill_code="data.cleaning", name_zh="数据清洗", category=SkillCategory.DATA),
        ]
    )
    db.commit()
    return db


def _draft(**overrides) -> CompetencyGraphDraft:
    skill = NodeDraft(
        node_type=NodeType.SKILL_POINT,
        name="视觉数据标注",
        skill_code="annot.image",
        mastery_level=3,
    )
    unit = NodeDraft(
        node_type=NodeType.COMPETENCY_UNIT,
        name="原始数据清洗与标注",
        evidence_markers=["S1"],
        children=[skill],
    )
    competency = NodeDraft(
        node_type=NodeType.COMPETENCY,
        name="数据标注能力",
        evidence_markers=["S1"],
        children=[unit],
    )
    second = NodeDraft(
        node_type=NodeType.COMPETENCY,
        name="数据处理能力",
        children=[
            NodeDraft(
                node_type=NodeType.COMPETENCY_UNIT,
                name="数据清洗",
                children=[
                    NodeDraft(
                        node_type=NodeType.SKILL_POINT,
                        name="数据清洗",
                        skill_code="data.cleaning",
                        mastery_level=2,
                    )
                ],
            )
        ],
    )
    return CompetencyGraphDraft(
        summary=overrides.get("summary", "测试图谱"),
        competencies=overrides.get("competencies", [competency, second]),
    )


def _persist(db: Session, draft: CompetencyGraphDraft):
    service = CompetencyGraphService(db)
    result = service.persist_draft(
        job=db.get(Job, "ai_data_annotator"), draft=draft, sources=SOURCES
    )
    db.commit()
    return service, result


# ---------------------------------------------------------------- Schema
def test_draft_rejects_ungeneratable_node_type() -> None:
    """job 根节点由服务端创建，不允许模型生成。"""
    with pytest.raises(ValueError, match="不允许由模型生成"):
        NodeDraft(node_type=NodeType.JOB, name="岗位")


def test_draft_requires_minimum_competencies() -> None:
    with pytest.raises(ValueError):
        CompetencyGraphDraft(competencies=[])


def test_mastery_level_is_bounded() -> None:
    with pytest.raises(ValueError):
        NodeDraft(node_type=NodeType.SKILL_POINT, name="x", mastery_level=9)


# ---------------------------------------------------------------- 持久化
def test_persist_creates_job_root_and_tree(seeded: Session) -> None:
    _, result = _persist(seeded, _draft())
    graph = result.graph

    assert graph.status is GraphStatus.DRAFT  # 默认必须是草案
    assert graph.version == 1

    roots = [n for n in graph.nodes if n.parent_id is None]
    assert len(roots) == 1
    assert roots[0].node_type is NodeType.JOB
    assert roots[0].ai_generated is False  # 根节点是服务端建的，不是 AI 生成


def test_node_ids_are_server_assigned_and_prefixed(seeded: Session) -> None:
    """ID 是下游全部外键的锚点，必须由服务端确定性分配。"""
    _, result = _persist(seeded, _draft())
    ids = {n.id for n in result.graph.nodes}
    assert all(i.startswith("g_ai_data_annotator_v1.") for i in ids)
    assert "g_ai_data_annotator_v1.cap1" in ids
    assert "g_ai_data_annotator_v1.sp1" in ids


def test_evidence_is_attached_from_markers(seeded: Session) -> None:
    _, result = _persist(seeded, _draft())
    node = next(n for n in result.graph.nodes if n.name == "数据标注能力")

    assert len(node.evidence) == 1
    assert node.evidence[0]["chunk_id"] == "doc_std#10"
    assert node.evidence[0]["page"] == "6"


def test_unknown_evidence_marker_is_ignored_with_warning(seeded: Session) -> None:
    """模型引用不存在的编号时不能当作它有依据。"""
    draft = _draft()
    draft.competencies[0].evidence_markers = ["S1", "S99"]
    _, result = _persist(seeded, draft)

    node = next(n for n in result.graph.nodes if n.name == "数据标注能力")
    assert len(node.evidence) == 1
    assert any("S99" in w for w in result.warnings)


# ------------------------------------------------------- 技能编码校验
def test_unknown_skill_code_node_is_dropped(seeded: Session) -> None:
    """无法 join 的技能点留着只会制造「看起来很完整」的假象。"""
    draft = _draft()
    draft.competencies[0].children[0].children.append(
        NodeDraft(
            node_type=NodeType.SKILL_POINT,
            name="量子标注",
            skill_code="annot.quantum",
            mastery_level=3,
        )
    )
    _, result = _persist(seeded, draft)

    names = {n.name for n in result.graph.nodes}
    assert "量子标注" not in names
    assert any("量子标注" in w and "已丢弃" in w for w in result.warnings)


def test_skill_code_is_normalised_from_alias(seeded: Session) -> None:
    """模型写了别名而非规范编码时，归一化而不是直接丢弃。"""
    draft = _draft()
    draft.competencies[0].children[0].children[0].skill_code = "图像标注"
    _, result = _persist(seeded, draft)

    node = next(n for n in result.graph.nodes if n.node_type is NodeType.SKILL_POINT)
    assert node.skill_code == "annot.image"
    assert any("归一为" in w for w in result.warnings)


def test_warns_when_no_skill_point_survives(seeded: Session) -> None:
    draft = _draft(
        competencies=[
            NodeDraft(
                node_type=NodeType.COMPETENCY,
                name="能力A",
                children=[
                    NodeDraft(
                        node_type=NodeType.COMPETENCY_UNIT,
                        name="单元A",
                        children=[
                            NodeDraft(
                                node_type=NodeType.SKILL_POINT,
                                name="不存在的技能",
                                skill_code="nope.nothing",
                            )
                        ],
                    )
                ],
            ),
            NodeDraft(node_type=NodeType.COMPETENCY, name="能力B"),
        ]
    )
    _, result = _persist(seeded, draft)
    assert any("没有任何技能点通过校验" in w for w in result.warnings)


# ---------------------------------------------------------------- 审核
def test_approve_marks_graph_and_records_reviewer(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    graph = service.approve(result.graph.id, "张老师")
    seeded.commit()

    assert graph.status is GraphStatus.APPROVED
    assert graph.approved_by == "张老师"
    assert graph.approved_at is not None


def test_approving_twice_is_rejected(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    service.approve(result.graph.id, "张老师")
    seeded.commit()

    with pytest.raises(ConflictError):
        service.approve(result.graph.id, "李老师")


def test_draft_can_be_deleted_but_approved_graph_cannot(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    graph_id = result.graph.id
    service.delete_draft(graph_id)
    seeded.commit()
    assert seeded.get(CompetencyGraph, graph_id) is None

    _, approved = _persist(seeded, _draft())
    service.approve(approved.graph.id, "张老师")
    seeded.commit()
    with pytest.raises(ConflictError):
        service.delete_draft(approved.graph.id)


def test_approve_archives_previous_version(seeded: Session) -> None:
    """同一岗位只保留一份 approved，否则下游不知道该引用哪份。"""
    service, first = _persist(seeded, _draft())
    service.approve(first.graph.id, "张老师")
    seeded.commit()

    _, second = _persist(seeded, _draft())
    service.approve(second.graph.id, "张老师")
    seeded.commit()

    assert seeded.get(CompetencyGraph, first.graph.id).status is GraphStatus.ARCHIVED
    assert seeded.get(CompetencyGraph, second.graph.id).status is GraphStatus.APPROVED
    assert second.graph.version == 2


def test_cannot_approve_graph_without_skill_points(seeded: Session) -> None:
    """没有技能点的图谱无法作为测评基线，不该放行。"""
    draft = _draft(
        competencies=[
            NodeDraft(node_type=NodeType.COMPETENCY, name="能力A"),
            NodeDraft(node_type=NodeType.COMPETENCY, name="能力B"),
        ]
    )
    service, result = _persist(seeded, draft)

    with pytest.raises(ValidationError, match="没有任何带技能编码的技能点"):
        service.approve(result.graph.id, "张老师")


# ------------------------------------------------- Target Skill Vector
def test_target_skill_vector_takes_highest_mastery(seeded: Session) -> None:
    """同一技能在多处出现时取最高要求 —— 这是学生测评的目标基线。"""
    draft = _draft()
    draft.competencies[1].children[0].children.append(
        NodeDraft(
            node_type=NodeType.SKILL_POINT,
            name="视觉数据标注",
            skill_code="annot.image",
            mastery_level=4,  # 比第一处的 3 更高
        )
    )
    service, result = _persist(seeded, draft)

    vector = service.target_skill_vector(result.graph)
    assert vector["annot.image"] == 4
    assert vector["data.cleaning"] == 2


def test_graph_delete_cascades(seeded: Session) -> None:
    _, result = _persist(seeded, _draft())
    graph_id = result.graph.id
    seeded.delete(seeded.get(CompetencyGraph, graph_id))
    seeded.commit()

    remaining = (
        seeded.query(CompetencyNode).filter(CompetencyNode.graph_id == graph_id).count()
    )
    assert remaining == 0


# ---------------------------------------------------------------- 编辑
def test_update_node_marks_human_edited(seeded: Session) -> None:
    """人工改过要留痕：演示时能说清哪些是 AI 生成、哪些经教师修订。"""
    service, result = _persist(seeded, _draft())
    node = next(n for n in result.graph.nodes if n.name == "数据标注能力")

    updated = service.update_node(result.graph.id, node.id, {"name": "数据标注核心能力"})
    seeded.commit()

    assert updated.name == "数据标注核心能力"
    assert updated.edited_by_human is True
    assert updated.ai_generated is True  # 出身仍是 AI，只是被改过


def test_cannot_edit_approved_graph(seeded: Session) -> None:
    """「审核后 ID 冻结」是下游敢引用它的全部理由，不能破例。"""
    service, result = _persist(seeded, _draft())
    node = next(n for n in result.graph.nodes if n.node_type is NodeType.COMPETENCY)
    service.approve(result.graph.id, "张老师")
    seeded.commit()

    with pytest.raises(ConflictError, match="只有草案可以修改"):
        service.update_node(result.graph.id, node.id, {"name": "改个名"})


def test_update_rejects_unknown_skill_code(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    node = next(n for n in result.graph.nodes if n.node_type is NodeType.SKILL_POINT)

    with pytest.raises(ValidationError, match="不在技能表中"):
        service.update_node(result.graph.id, node.id, {"skill_code": "nope.nothing"})


def test_update_normalises_skill_alias(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    node = next(n for n in result.graph.nodes if n.node_type is NodeType.SKILL_POINT)

    updated = service.update_node(result.graph.id, node.id, {"skill_code": "图像标注"})
    seeded.commit()
    assert updated.skill_code == "annot.image"


def test_cannot_clear_skill_code_on_skill_point(seeded: Session) -> None:
    """技能点没有 skill_code 就无法 join，不允许清空。"""
    service, result = _persist(seeded, _draft())
    node = next(n for n in result.graph.nodes if n.node_type is NodeType.SKILL_POINT)

    with pytest.raises(ValidationError, match="必须保留技能编码"):
        service.update_node(result.graph.id, node.id, {"skill_code": None})


def test_create_node_is_marked_human_authored(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    parent = next(n for n in result.graph.nodes if n.node_type is NodeType.COMPETENCY_UNIT)

    node = service.create_node(
        result.graph.id,
        {
            "parent_id": parent.id,
            "node_type": NodeType.SKILL_POINT,
            "name": "文本数据标注",
            "skill_code": "annot.text",
            "mastery_level": 3,
        },
    )
    seeded.commit()

    assert node.ai_generated is False  # 教师加的，不是 AI 生成
    assert node.edited_by_human is True
    assert node.id.startswith(f"{result.graph.id}.sp")


def test_create_skill_point_requires_skill_code(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    parent = next(n for n in result.graph.nodes if n.node_type is NodeType.COMPETENCY_UNIT)

    with pytest.raises(ValidationError, match="必须指定技能编码"):
        service.create_node(
            result.graph.id,
            {"parent_id": parent.id, "node_type": NodeType.SKILL_POINT, "name": "无编码"},
        )


def test_delete_node_removes_descendants(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    competency = next(n for n in result.graph.nodes if n.name == "数据标注能力")

    removed = service.delete_node(result.graph.id, competency.id)
    seeded.commit()

    assert removed == 3  # 能力 + 能力单元 + 技能点
    assert seeded.get(CompetencyNode, competency.id) is None


def test_cannot_delete_job_root(seeded: Session) -> None:
    service, result = _persist(seeded, _draft())
    root = next(n for n in result.graph.nodes if n.parent_id is None)

    with pytest.raises(ValidationError, match="不能删除岗位根节点"):
        service.delete_node(result.graph.id, root.id)
