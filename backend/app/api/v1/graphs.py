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
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.competency import CompetencyGraph, CompetencyNode
from app.models.job_market import JobPosting, JobPostingSkill
from app.models.ontology import Job, Skill
from app.schemas.common import Page
from app.schemas.competency import (
    ApproveGraphRequest,
    GenerateGraphRequest,
    GraphDetail,
    GraphSummary,
    NodeRead,
)
from app.schemas.competency_edit import (
    JobEvidenceCandidateRead,
    LinkJobEvidenceRequest,
    NodeCreateRequest,
    NodeUpdateRequest,
)
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

    selected_codes = list(dict.fromkeys(payload.selected_skill_codes))
    if selected_codes:
        selected_set = set(selected_codes)
        skills = [skill for skill in skills if skill.skill_code in selected_set]
        found_codes = {skill.skill_code for skill in skills}
        missing_codes = selected_set - found_codes
        if missing_codes:
            raise ValidationError(
                "所选能力中存在不可用的技能编码，请返回岗位需求分析后重新选择。",
                detail={"missing_skill_codes": sorted(missing_codes)},
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
        allowed_skill_codes=set(selected_codes) if selected_codes else None,
        selected_skill_codes=selected_codes,
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


def _job_evidence_candidates(
    db: Session, graph: CompetencyGraph, node: CompetencyNode
) -> list[tuple[JobPostingSkill, JobPosting]]:
    if not node.skill_code:
        raise ValidationError("只有带技能编码的技能点或知识点可以关联岗位原文。")
    return db.execute(
        select(JobPostingSkill, JobPosting)
        .join(JobPosting, JobPosting.id == JobPostingSkill.posting_id)
        .where(
            JobPosting.job_id == graph.job_id,
            JobPostingSkill.skill_code == node.skill_code,
        )
        .order_by(JobPosting.posted_at.desc(), JobPosting.id)
        .limit(20)
    ).all()


@router.get(
    "/{graph_id}/nodes/{node_id}/job-evidence-candidates",
    response_model=list[JobEvidenceCandidateRead],
    summary="查询可关联的岗位原文",
)
def job_evidence_candidates(
    graph_id: str, node_id: str, db: Session = Depends(get_db)
) -> list[JobEvidenceCandidateRead]:
    graph = db.get(CompetencyGraph, graph_id)
    node = db.get(CompetencyNode, node_id)
    if graph is None or node is None or node.graph_id != graph_id:
        raise NotFoundError("未找到图谱节点", detail={"graph_id": graph_id, "node_id": node_id})
    return [
        JobEvidenceCandidateRead(
            posting_id=posting.id,
            title=posting.title,
            city=posting.city,
            posted_at=posting.posted_at.isoformat() if posting.posted_at else None,
            source_name=posting.source_name,
            source_url=posting.source_url,
            evidence_span=link.evidence_span,
        )
        for link, posting in _job_evidence_candidates(db, graph, node)
    ]


@router.post(
    "/{graph_id}/nodes/{node_id}/job-evidence",
    response_model=NodeRead,
    summary="关联岗位原文作为节点依据",
)
def link_job_evidence(
    graph_id: str,
    node_id: str,
    payload: LinkJobEvidenceRequest,
    db: Session = Depends(get_db),
) -> NodeRead:
    graph = db.get(CompetencyGraph, graph_id)
    node = db.get(CompetencyNode, node_id)
    if graph is None or node is None or node.graph_id != graph_id:
        raise NotFoundError("未找到图谱节点", detail={"graph_id": graph_id, "node_id": node_id})
    if graph.status is not GraphStatus.DRAFT:
        raise ConflictError("已审核或已归档图谱不可修改依据；请生成新草稿后再调整。")

    candidate_by_id = {posting.id: (link, posting) for link, posting in _job_evidence_candidates(db, graph, node)}
    selected_ids = list(dict.fromkeys(payload.posting_ids))
    missing_ids = set(selected_ids) - set(candidate_by_id)
    if missing_ids:
        raise ValidationError("所选岗位原文与当前节点技能不匹配。", detail={"posting_ids": sorted(missing_ids)})

    job_evidence = []
    for posting_id in selected_ids:
        link, posting = candidate_by_id[posting_id]
        job_evidence.append(
            {
                "type": "job_posting",
                "posting_id": posting.id,
                "source_name": posting.source_name,
                "source_url": posting.source_url,
                "section": posting.title,
                "page": posting.posted_at.date().isoformat() if posting.posted_at else None,
                "quote": link.evidence_span,
            }
        )
    node.evidence = [item for item in node.evidence if item.get("type") != "job_posting"] + job_evidence
    node.edited_by_human = True
    db.commit()
    db.refresh(node)
    return NodeRead.from_node(node, [NodeRead.from_node(child) for child in node.children])


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


@router.delete(
    "/{graph_id}",
    summary="删除图谱草稿",
    description="仅可删除未审核通过的草稿图谱；关联节点将一并删除。",
)
def delete_graph(graph_id: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    CompetencyGraphService(db).delete_draft(graph_id)
    db.commit()
    return {"deleted": True}


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
