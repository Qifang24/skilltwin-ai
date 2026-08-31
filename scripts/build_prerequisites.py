"""推断并写入技能前置依赖 → competency_edge。

    python scripts/build_prerequisites.py
    python scripts/build_prerequisites.py --dry-run
    python scripts/build_prerequisites.py --reset      # 先清空已有 prereq 边

模型只提出候选，**采纳与否由无环校验决定**：
逐条尝试加入，若某条会让依赖图成环则拒绝并说明。
前置关系一旦成环，拓扑排序无解，学习路径就排不出先后。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import delete, select  # noqa: E402

from app.agents.prerequisite import PrereqInput, PrerequisiteAgent  # noqa: E402
from app.core.config import DemoMode, settings  # noqa: E402
from app.core.db import create_all, session_scope  # noqa: E402
from app.core.enums import (  # noqa: E402
    SKILL_BEARING_NODE_TYPES,
    EdgeRelation,
    GraphStatus,
)
from app.core.llm import build_provider  # noqa: E402
from app.core.llm_runner import LLMRunner  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.competency import CompetencyEdge, CompetencyGraph, CompetencyNode  # noqa: E402
from app.models.ontology import Job, Skill  # noqa: E402
from app.services.path_ordering import find_cycles  # noqa: E402
from app.services.skill_normalizer import SkillNormalizer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="推断技能前置依赖")
    parser.add_argument("--job", default="ai_data_annotator")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true", help="先清空已有 prereq 边")
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging("WARNING")
    create_all()

    if not settings.llm_api_key:
        print("❌ 未配置 LLM_API_KEY")
        return 1

    with session_scope() as db:
        job = db.get(Job, args.job)
        graph = db.execute(
            select(CompetencyGraph).where(
                CompetencyGraph.job_id == args.job,
                CompetencyGraph.status == GraphStatus.APPROVED,
            )
        ).scalars().first()
        if job is None or graph is None:
            print(f"❌ 岗位 {args.job} 无已审核图谱")
            return 1

        # 技能点节点：前置关系建在它们之间
        skill_nodes = {
            n.skill_code: n
            for n in graph.nodes
            if n.skill_code and n.node_type in SKILL_BEARING_NODE_TYPES
        }
        skills = []
        for code in sorted(skill_nodes):
            skill = db.get(Skill, code)
            if skill:
                skills.append((code, skill.name_zh, skill.category.value))

        print(f"岗位：{job.name}  图谱：{graph.id}")
        print(f"技能点：{len(skills)} 个\n")

        if args.reset and not args.dry_run:
            db.execute(
                delete(CompetencyEdge).where(
                    CompetencyEdge.graph_id == graph.id,
                    CompetencyEdge.relation == EdgeRelation.PREREQ,
                )
            )
            db.flush()
            print("已清空原有 prereq 边\n")

        agent = PrerequisiteAgent(
            runner=LLMRunner(provider=build_provider(), demo_mode=DemoMode.RECORD)
        )
        envelope = agent.run(
            db, PrereqInput(job_name=job.name, skills=skills, max_pairs=14)
        )

        normalizer = SkillNormalizer(db)
        accepted: list[tuple[str, str, str]] = []
        rejected: list[tuple[str, str, str]] = []
        edges: list[tuple[str, str]] = []
        codes = set(skill_nodes)

        for pair in envelope.result.pairs:
            prereq = normalizer.resolve(pair.prerequisite)
            target = normalizer.resolve(pair.target)

            if prereq is None or target is None:
                rejected.append((pair.prerequisite, pair.target, "技能编码不存在"))
                continue
            if prereq == target:
                rejected.append((prereq, target, "自指"))
                continue
            if prereq not in codes or target not in codes:
                rejected.append((prereq, target, "不在本图谱的技能点中"))
                continue
            if (prereq, target) in edges:
                rejected.append((prereq, target, "重复"))
                continue

            # 无环校验：逐条试加，成环就拒
            trial = [*edges, (prereq, target)]
            if find_cycles(trial, codes):
                rejected.append((prereq, target, "会造成循环依赖"))
                continue

            edges.append((prereq, target))
            accepted.append((prereq, target, pair.reason))

        print(f"模型提出 {len(envelope.result.pairs)} 条，采纳 {len(accepted)} 条：\n")
        for prereq, target, reason in accepted:
            print(f"  {prereq:28s} → {target:28s}")
            print(f"  {'':28s}   {reason[:60]}")
        if rejected:
            print(f"\n⚠️  拒绝 {len(rejected)} 条：")
            for prereq, target, why in rejected:
                print(f"     {prereq} → {target}  —  {why}")

        if args.dry_run:
            print("\n（--dry-run，未写库）")
            return 0

        for prereq, target, reason in accepted:
            db.add(
                CompetencyEdge(
                    graph_id=graph.id,
                    from_node_id=skill_nodes[prereq].id,
                    to_node_id=skill_nodes[target].id,
                    relation=EdgeRelation.PREREQ,
                    note=reason,
                )
            )
        db.flush()

    print(f"\n已写入 {len(accepted)} 条前置依赖")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
