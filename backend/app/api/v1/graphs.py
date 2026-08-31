"""岗位能力图谱接口。

生命周期：`POST /generate` 产出 draft → 教师审核修改 → `POST /approve` 固化。
**只有 approved 的图谱可被下游引用**，因为只有它的节点 ID 是冻结的。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.agents.competency_graph import CompetencyGraphAgent, GraphGenerationInput
from app.core.db import get_db
from app.core.enums import SKILL_BEARING_NODE_TYPES, GraphStatus, SkillStatus
from app.core.errors import NotFoundError, ValidationError
from app.models.competency import CompetencyGraph, CompetencyNode
from app.models.ontology import Job, Skill
from app.schemas.common import Page
from app.schemas.competency import (
    ApproveGraphRequest,
    GenerateGraphRequest,
    GraphDetail,
    GraphSummary,
    NodeRead,
)
from app.schemas.competency_edit import NodeCreateRequest, NodeUpdateRequest
from app.services.competency_graph_service import CompetencyGraphService

router = APIRouter(prefix="/graphs", tags=["competency-graph"])


def _build_tree(nodes: list[CompetencyNode]) -> list[NodeRead]:
    """把扁平节点列表还原成嵌套树，供前端直接渲染。"""
    by_parent: dict[str | None, list[CompetencyNode]] = {}
    for node in sorted(nodes, key=lambda n: (n.order_index, n.id)):
        by_parent.setdefault(node.parent_id, []).append(node)

    def build(node: CompetencyNode) -> NodeRead:
        return NodeRead.from_node(
            node, [build(child) for child in by_parent.get(node.id, [])]
        )

    return [build(root) for root in by_parent.get(None, [])]


def _summarise(graph: CompetencyGraph) -> GraphSummary:
    item = GraphSummary.model_validate(graph)
    item.node_count = len(graph.nodes)
    item.skill_point_count = sum(
        1 for n in graph.nodes if n.node_type in SKILL_BEARING_NODE_TYPES
    )
    return item


@router.post(
    "/generate",
    response_model=GraphDetail,
    summary="生成能力图谱草案",
    description=(
        "结合职业标准检索结果与技能规范表生成草案，状态为 draft。"
        "技能点只能引用技能表中已有的编码，无法解析的节点会被丢弃并在 warnings 中说明。"
    ),
)
def generate_graph(
    payload: GenerateGraphRequest, db: Session = Depends(get_db)
) -> GraphDetail:
    job = db.get(Job, payload.job_id)
    if job is None:
        raise NotFoundError(
            f"未找到岗位：{payload.job_id}", detail={"job_id": payload.job_id}
        )

    skills = (
        db.execute(
            select(Skill)
            .where(Skill.status == SkillStatus.ACTIVE)
            .order_by(Skill.category, Skill.skill_code)
        )
        .scalars()
        .all()
    )
    if not skills:
        raise ValidationError(
            "技能表为空，无法生成图谱。请先运行 scripts/seed_skills.py 载入技能规范表"
        )

    agent = CompetencyGraphAgent()
    envelope = agent.run(
        db,
        GraphGenerationInput(
            job_id=job.id,
            job_name=job.name,
            available_skills=[
                (s.skill_code, s.name_zh, s.category.value) for s in skills
            ],
            focus=payload.focus,
        ),
    )

    service = CompetencyGraphService(db)
    result = service.persist_draft(
        job=job,
        draft=envelope.result,
        sources=envelope.sources,
        generation_run_id=envelope.llm_run_id,
    )
    db.commit()
    db.refresh(result.graph)

    detail = GraphDetail(**_summarise(result.graph).model_dump())
    detail.tree = _build_tree(result.graph.nodes)
    detail.sources = envelope.sources
    detail.generation_run_id = envelope.llm_run_id
    detail.warnings = [*envelope.warnings, *result.warnings]
    return detail


@router.get("", response_model=Page[GraphSummary], summary="图谱列表")
def list_graphs(
    db: Session = Depends(get_db),
    job_id: str | None = Query(default=None),
    status: GraphStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[GraphSummary]:
    filters = []
    if job_id:
        filters.append(CompetencyGraph.job_id == job_id)
    if status:
        filters.append(CompetencyGraph.status == status)

    total = db.execute(
        select(func.count()).select_from(CompetencyGraph).where(*filters)
    ).scalar_one()
    graphs = (
        db.execute(
            select(CompetencyGraph)
            .options(selectinload(CompetencyGraph.nodes))
            .where(*filters)
            .order_by(CompetencyGraph.job_id, CompetencyGraph.version.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return Page[GraphSummary](
        items=[_summarise(g) for g in graphs], total=total, limit=limit, offset=offset
    )


@router.get(
    "/{graph_id}",
    response_model=GraphDetail,
    summary="图谱详情",
    description="返回可直接渲染的嵌套树结构。",
)
def get_graph(graph_id: str, db: Session = Depends(get_db)) -> GraphDetail:
    graph = db.execute(
        select(CompetencyGraph)
        .options(selectinload(CompetencyGraph.nodes))
        .where(CompetencyGraph.id == graph_id)
    ).scalar_one_or_none()
    if graph is None:
        raise NotFoundError(f"未找到图谱：{graph_id}", detail={"graph_id": graph_id})

    detail = GraphDetail(**_summarise(graph).model_dump())
    detail.tree = _build_tree(graph.nodes)
    detail.generation_run_id = graph.generation_run_id
    return detail


@router.get(
    "/{graph_id}/nodes/{node_id}",
    response_model=NodeRead,
    summary="节点详情",
    description="含该节点的依据引用，回答「这项能力凭什么在图谱里」。",
)
def get_node(graph_id: str, node_id: str, db: Session = Depends(get_db)) -> NodeRead:
    node = db.get(CompetencyNode, node_id)
    if node is None or node.graph_id != graph_id:
        raise NotFoundError(
            f"未找到节点：{node_id}", detail={"graph_id": graph_id, "node_id": node_id}
        )
    return NodeRead.from_node(node, [NodeRead.from_node(c) for c in node.children])


@router.patch(
    "/{graph_id}/nodes/{node_id}",
    response_model=NodeRead,
    summary="修改节点",
    description="仅草案可改。修改后节点会被标记为 edited_by_human。",
)
def update_node(
    graph_id: str,
    node_id: str,
    payload: NodeUpdateRequest,
    db: Session = Depends(get_db),
) -> NodeRead:
    changes = payload.model_dump(exclude_unset=True)
    node = CompetencyGraphService(db).update_node(graph_id, node_id, changes)
    db.commit()
    db.refresh(node)
    return NodeRead.from_node(node)


@router.post(
    "/{graph_id}/nodes",
    response_model=NodeRead,
    status_code=201,
    summary="新增节点",
    description="教师补充模型遗漏的能力。仅草案可加。",
)
def create_node(
    graph_id: str, payload: NodeCreateRequest, db: Session = Depends(get_db)
) -> NodeRead:
    node = CompetencyGraphService(db).create_node(graph_id, payload.model_dump())
    db.commit()
    db.refresh(node)
    return NodeRead.from_node(node)


@router.delete(
    "/{graph_id}/nodes/{node_id}",
    summary="删除节点",
    description="连同其全部子节点一并删除。仅草案可删。",
)
def delete_node(
    graph_id: str, node_id: str, db: Session = Depends(get_db)
) -> dict[str, int]:
    removed = CompetencyGraphService(db).delete_node(graph_id, node_id)
    db.commit()
    return {"removed": removed}


@router.post(
    "/{graph_id}/approve",
    response_model=GraphSummary,
    summary="审核通过图谱",
    description=(
        "draft → approved。通过后节点 ID 冻结，可被课程映射、实训任务、"
        "学生能力向量引用。同一岗位的旧 approved 图谱会自动归档。"
    ),
)
def approve_graph(
    graph_id: str, payload: ApproveGraphRequest, db: Session = Depends(get_db)
) -> GraphSummary:
    service = CompetencyGraphService(db)
    graph = service.approve(graph_id, payload.approved_by)
    db.commit()
    db.refresh(graph)
    return _summarise(graph)


@router.get(
    "/{graph_id}/target-vector",
    response_model=dict[str, int],
    summary="目标能力向量",
    description=(
        "图谱 → Target Skill Vector，教师侧与学生侧的连接点："
        "同一份图谱既是课程对标基准，也是学生测评的目标基线。"
    ),
)
def target_vector(graph_id: str, db: Session = Depends(get_db)) -> dict[str, int]:
    graph = db.execute(
        select(CompetencyGraph)
        .options(selectinload(CompetencyGraph.nodes))
        .where(CompetencyGraph.id == graph_id)
    ).scalar_one_or_none()
    if graph is None:
        raise NotFoundError(f"未找到图谱：{graph_id}", detail={"graph_id": graph_id})
    return CompetencyGraphService(db).target_skill_vector(graph)
