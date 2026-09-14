"""能力图谱的持久化与生命周期管理。

三件事在这里把关，缺一样图谱都不能作为「数据中枢」：

  1. **节点 ID 由服务端确定性分配**，不用模型给的。ID 是课程映射、
     实训任务、学生能力向量的共同外键，必须稳定。
  2. **技能编码必须解析到技能表**。解析不了的技能点直接丢弃 ——
     一个没有 skill_code 的技能点在下游无法 join，留着只会制造幻觉般的完整感。
  3. **只有 approved 的图谱可被下游引用**。draft 随便改，approve 后 ID 冻结。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import GraphStatus, NodeType, SKILL_BEARING_NODE_TYPES
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.competency import CompetencyGraph, CompetencyNode
from app.models.job_market import JobPosting, JobPostingSkill
from app.models.ontology import Job, Skill
from app.schemas.common import SourceRef
from app.schemas.competency import CompetencyGraphDraft, NodeDraft
from app.services.skill_normalizer import SkillNormalizer

logger = get_logger(__name__)

_TYPE_ABBREV = {
    NodeType.JOB: "job",
    NodeType.WORK_TASK: "task",
    NodeType.COMPETENCY: "cap",
    NodeType.COMPETENCY_UNIT: "unit",
    NodeType.SKILL_POINT: "sp",
    NodeType.KNOWLEDGE_POINT: "kp",
}


@dataclass
class PersistResult:
    graph: CompetencyGraph
    warnings: list[str]


class CompetencyGraphService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------ 版本
    def next_version(self, job_id: str) -> int:
        current = self._db.execute(
            select(CompetencyGraph.version)
            .where(CompetencyGraph.job_id == job_id)
            .order_by(CompetencyGraph.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        return (current or 0) + 1

    def graph_id_for(self, job_id: str, version: int) -> str:
        return f"g_{job_id}_v{version}"

    # ------------------------------------------------------------ 持久化
    def persist_draft(
        self,
        *,
        job: Job,
        draft: CompetencyGraphDraft,
        sources: list[SourceRef],
        generation_run_id: str | None = None,
        allowed_skill_codes: set[str] | None = None,
        selected_skill_codes: list[str] | None = None,
    ) -> PersistResult:
        version = self.next_version(job.id)
        graph_id = self.graph_id_for(job.id, version)

        graph = CompetencyGraph(
            id=graph_id,
            job_id=job.id,
            version=version,
            status=GraphStatus.DRAFT,
            title=f"{job.name}_能力图谱 v{version}",
            summary=draft.summary or None,
            generation_run_id=generation_run_id,
            selected_skill_codes=list(dict.fromkeys(selected_skill_codes or [])),
        )
        self._db.add(graph)
        self._db.flush()

        normalizer = SkillNormalizer(self._db)
        marker_map = {s.marker: s for s in sources if s.marker}
        counters: dict[str, int] = {}
        warnings: list[str] = []
        job_evidence_cache: dict[str, list[dict]] = {}

        def job_evidence_for(skill_code: str) -> list[dict]:
            if skill_code not in job_evidence_cache:
                rows = self._db.execute(
                    select(JobPostingSkill, JobPosting)
                    .join(JobPosting, JobPosting.id == JobPostingSkill.posting_id)
                    .where(
                        JobPosting.job_id == job.id,
                        JobPostingSkill.skill_code == skill_code,
                    )
                    .order_by(JobPosting.posted_at.desc(), JobPosting.id)
                ).all()
                job_evidence_cache[skill_code] = [
                    {
                        "type": "job_posting",
                        "posting_id": posting.id,
                        "source_name": posting.source_name,
                        "source_url": posting.source_url,
                        "section": posting.title,
                        "page": posting.posted_at.date().isoformat() if posting.posted_at else None,
                        "quote": link.evidence_span,
                    }
                    for link, posting in rows
                ]
            return job_evidence_cache[skill_code]

        # 根节点：岗位本身。由服务端创建，不交给模型。
        root = CompetencyNode(
            id=f"{graph_id}.{_TYPE_ABBREV[NodeType.JOB]}",
            graph_id=graph_id,
            node_type=NodeType.JOB,
            name=job.name,
            description=job.description,
            order_index=0,
            ai_generated=False,
        )
        self._db.add(root)

        def next_id(node_type: NodeType) -> str:
            abbrev = _TYPE_ABBREV[node_type]
            counters[abbrev] = counters.get(abbrev, 0) + 1
            return f"{graph_id}.{abbrev}{counters[abbrev]}"

        def evidence_for(node: NodeDraft) -> list[dict]:
            items = []
            for marker in node.evidence_markers:
                source = marker_map.get(marker)
                if source is None:
                    # 模型引用了不存在的编号 —— 记下来，但不当作它有依据
                    warnings.append(
                        f"节点「{node.name}」引用了不存在的依据编号 {marker}，已忽略"
                    )
                    continue
                items.append(
                    {
                        "chunk_id": source.chunk_id,
                        "page": source.page,
                        "section": source.section,
                        "source_name": source.source_name,
                        "quote": source.quote,
                    }
                )
            return items

        def walk(node: NodeDraft, parent_id: str, order: int) -> None:
            skill_code = None
            if node.is_skill_bearing:
                skill_code = self._resolve_skill(
                    node, normalizer, warnings, allowed_skill_codes=allowed_skill_codes
                )
                if skill_code is None:
                    # 无法 join 的技能点留着只会制造「看起来很完整」的假象
                    return

            node_id = next_id(node.node_type)
            self._db.add(
                CompetencyNode(
                    id=node_id,
                    graph_id=graph_id,
                    parent_id=parent_id,
                    node_type=node.node_type,
                    name=node.name,
                    description=node.description,
                    skill_code=skill_code,
                    mastery_level=node.mastery_level,
                    order_index=order,
                    evidence=(
                        evidence_for(node) + job_evidence_for(skill_code)
                        if skill_code else evidence_for(node)
                    ),
                    ai_generated=True,
                )
            )
            for child_order, child in enumerate(node.children):
                walk(child, node_id, child_order)

        for order, competency in enumerate(draft.competencies):
            walk(competency, root.id, order)

        self._db.flush()

        kept = self._db.execute(
            select(CompetencyNode).where(CompetencyNode.graph_id == graph_id)
        ).scalars().all()
        skill_points = [n for n in kept if n.node_type in SKILL_BEARING_NODE_TYPES]

        if not skill_points:
            warnings.append(
                "本次生成没有任何技能点通过校验，图谱无法支撑下游能力测评，建议重新生成"
            )

        logger.info(
            "图谱草案已入库",
            extra={
                "graph_id": graph_id,
                "nodes": len(kept),
                "skill_points": len(skill_points),
                "warnings": len(warnings),
            },
        )
        return PersistResult(graph=graph, warnings=warnings)

    def _resolve_skill(
        self,
        node: NodeDraft,
        normalizer: SkillNormalizer,
        warnings: list[str],
        *,
        allowed_skill_codes: set[str] | None = None,
    ) -> str | None:
        """把模型给的技能编码解析到技能表。

        先试它给的 code，再试节点名称 —— 模型有时会把名称写进 skill_code 字段。
        两者都解析不了就返回 None，该节点会被丢弃。
        """
        for candidate in (node.skill_code, node.name):
            if not candidate:
                continue
            resolved = normalizer.resolve(candidate)
            if resolved:
                if allowed_skill_codes is not None and resolved not in allowed_skill_codes:
                    warnings.append(
                        f"节点「{node.name}」对应技能 {resolved} 未被纳入本次图谱，已跳过"
                    )
                    return None
                if node.skill_code and resolved != node.skill_code:
                    warnings.append(
                        f"节点「{node.name}」的技能编码 {node.skill_code} 已归一为 {resolved}"
                    )
                return resolved

        warnings.append(
            f"节点「{node.name}」的技能编码 {node.skill_code!r} 不在技能表中，该节点已丢弃"
        )
        return None

    # ------------------------------------------------------------ 编辑
    def _editable_graph(self, graph_id: str) -> CompetencyGraph:
        """取出可编辑的图谱。

        approved 图谱**不允许修改** —— 「审核通过后 ID 冻结」是下游敢于
        引用它的全部理由。要改就生成新版本，让旧版归档。
        """
        graph = self._db.get(CompetencyGraph, graph_id)
        if graph is None:
            raise NotFoundError(f"未找到图谱：{graph_id}", detail={"graph_id": graph_id})
        if graph.status is not GraphStatus.DRAFT:
            raise ConflictError(
                f"图谱当前状态为 {graph.status.value}，只有草案可以修改。"
                f"如需调整已审核的图谱，请重新生成一个新版本。",
                detail={"graph_id": graph_id, "status": graph.status.value},
            )
        return graph

    def _node_in_graph(self, graph_id: str, node_id: str) -> CompetencyNode:
        node = self._db.get(CompetencyNode, node_id)
        if node is None or node.graph_id != graph_id:
            raise NotFoundError(
                f"未找到节点：{node_id}",
                detail={"graph_id": graph_id, "node_id": node_id},
            )
        return node

    def update_node(self, graph_id: str, node_id: str, changes: dict) -> CompetencyNode:
        self._editable_graph(graph_id)
        node = self._node_in_graph(graph_id, node_id)

        if "skill_code" in changes:
            raw = changes["skill_code"]
            if raw:
                resolved = SkillNormalizer(self._db).resolve(raw)
                if resolved is None:
                    raise ValidationError(
                        f"技能编码 {raw!r} 不在技能表中。"
                        f"请先在技能表中添加该技能，或改用已有编码。",
                        detail={"skill_code": raw},
                    )
                changes["skill_code"] = resolved
            elif node.node_type in SKILL_BEARING_NODE_TYPES:
                raise ValidationError(
                    f"{node.node_type.value} 类型节点必须保留技能编码，"
                    f"否则下游无法关联。如需移除，请删除该节点。"
                )

        for field, value in changes.items():
            setattr(node, field, value)

        # 人工改过的节点要留痕：演示时能说清哪些是 AI 生成、哪些经教师修订
        node.edited_by_human = True
        self._db.flush()
        logger.info(
            "节点已修改",
            extra={"node_id": node_id, "fields": sorted(changes)},
        )
        return node

    def create_node(self, graph_id: str, payload: dict) -> CompetencyNode:
        graph = self._editable_graph(graph_id)
        parent = self._node_in_graph(graph_id, payload["parent_id"])

        node_type = payload["node_type"]
        skill_code = payload.get("skill_code")
        if node_type in SKILL_BEARING_NODE_TYPES:
            if not skill_code:
                raise ValidationError(
                    f"{node_type.value} 类型节点必须指定技能编码，否则下游无法关联"
                )
            resolved = SkillNormalizer(self._db).resolve(skill_code)
            if resolved is None:
                raise ValidationError(
                    f"技能编码 {skill_code!r} 不在技能表中",
                    detail={"skill_code": skill_code},
                )
            skill_code = resolved

        # 沿用与生成时相同的编号规则，避免手工节点的 ID 风格割裂
        abbrev = _TYPE_ABBREV[node_type]
        used = {
            n.id
            for n in graph.nodes
            if n.id.startswith(f"{graph_id}.{abbrev}")
        }
        seq = len(used) + 1
        while f"{graph_id}.{abbrev}{seq}" in used:
            seq += 1

        siblings = [n for n in graph.nodes if n.parent_id == parent.id]
        node = CompetencyNode(
            id=f"{graph_id}.{abbrev}{seq}",
            graph_id=graph_id,
            parent_id=parent.id,
            node_type=node_type,
            name=payload["name"],
            description=payload.get("description"),
            skill_code=skill_code,
            mastery_level=payload.get("mastery_level"),
            order_index=len(siblings),
            ai_generated=False,  # 教师手工添加，不是 AI 生成
            edited_by_human=True,
        )
        self._db.add(node)
        self._db.flush()
        logger.info("节点已新增", extra={"node_id": node.id, "parent": parent.id})
        return node

    def delete_node(self, graph_id: str, node_id: str) -> int:
        """删除节点及其全部子孙。返回删除数量。"""
        self._editable_graph(graph_id)
        node = self._node_in_graph(graph_id, node_id)

        if node.parent_id is None:
            raise ValidationError("不能删除岗位根节点")

        removed = self._count_descendants(node) + 1
        self._db.delete(node)  # cascade 会带走子孙
        self._db.flush()
        logger.info("节点已删除", extra={"node_id": node_id, "removed": removed})
        return removed

    def delete_draft(self, graph_id: str) -> None:
        """删除尚未审核通过的图谱草稿及其全部节点。"""
        graph = self._db.get(CompetencyGraph, graph_id)
        if graph is None:
            raise NotFoundError(f"未找到图谱：{graph_id}", detail={"graph_id": graph_id})
        if graph.status is not GraphStatus.DRAFT:
            raise ConflictError("仅草稿图谱可删除；已审核或已归档图谱需要保留以维持下游引用。")

        self._db.delete(graph)
        self._db.flush()
        logger.info("图谱草稿已删除", extra={"graph_id": graph_id})

    def _count_descendants(self, node: CompetencyNode) -> int:
        return sum(1 + self._count_descendants(c) for c in node.children)

    # ------------------------------------------------------------ 审核
    def approve(self, graph_id: str, approved_by: str) -> CompetencyGraph:
        graph = self._db.get(CompetencyGraph, graph_id)
        if graph is None:
            raise NotFoundError(f"未找到图谱：{graph_id}", detail={"graph_id": graph_id})
        if graph.status is GraphStatus.APPROVED:
            raise ConflictError("该图谱已通过审核，无需重复操作")
        if graph.status is GraphStatus.ARCHIVED:
            raise ConflictError("已归档的图谱不能再审核通过")

        skill_points = [
            n for n in graph.nodes if n.node_type in SKILL_BEARING_NODE_TYPES
        ]
        if not skill_points:
            raise ValidationError(
                "图谱中没有任何带技能编码的技能点，无法作为能力测评基线，不能通过审核",
                detail={"graph_id": graph_id},
            )

        # 同一岗位只保留一份 approved：旧的自动归档，避免下游不知道该引用哪份
        previous = self._db.execute(
            select(CompetencyGraph).where(
                CompetencyGraph.job_id == graph.job_id,
                CompetencyGraph.status == GraphStatus.APPROVED,
                CompetencyGraph.id != graph_id,
            )
        ).scalars().all()
        for old in previous:
            old.status = GraphStatus.ARCHIVED

        graph.status = GraphStatus.APPROVED
        graph.approved_by = approved_by
        graph.approved_at = utcnow()
        if previous:
            from app.models.curriculum import OptimizationRun
            self._db.execute(
                update(OptimizationRun)
                .where(
                    OptimizationRun.job_id == graph.job_id,
                    OptimizationRun.graph_id != graph_id,
                    OptimizationRun.is_stale.is_(False),
                )
                .values(is_stale=True)
            )
        self._db.flush()

        logger.info(
            "图谱已通过审核",
            extra={
                "graph_id": graph_id,
                "approved_by": approved_by,
                "archived": [g.id for g in previous],
            },
        )
        return graph

    # ------------------------------------------------------------ 查询
    def get_approved(self, job_id: str) -> CompetencyGraph | None:
        return self._db.execute(
            select(CompetencyGraph).where(
                CompetencyGraph.job_id == job_id,
                CompetencyGraph.status == GraphStatus.APPROVED,
            )
        ).scalars().first()

    def target_skill_vector(self, graph: CompetencyGraph) -> dict[str, int]:
        """图谱 → Target Skill Vector。

        这是教师侧与学生侧的连接点：同一份 approved 图谱，
        既是课程对标基准，也是学生能力测评的目标基线。
        同一技能在多处出现时取最高掌握要求。
        """
        vector: dict[str, int] = {}
        for node in graph.nodes:
            if node.skill_code and node.mastery_level:
                current = vector.get(node.skill_code, 0)
                vector[node.skill_code] = max(current, node.mastery_level)
        return vector
