"""生成诊断测评题库。

    python scripts/generate_items.py                    # 为已审核图谱涉及的技能出题
    python scripts/generate_items.py --per-skill 4      # 每个技能出几题
    python scripts/generate_items.py --dry-run

**为什么每个技能至少要 3~4 题**：能力估计是统计量，样本太小算不出可信结论。
1 题的估计置信度约 0.2，3 题约 0.44，都低于可信阈值 0.5。
题库薄的后果不是「估计差一点」，而是整份能力画像都不该被当真。
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.agents.assessment import AssessmentItemAgent, ItemGenerationInput  # noqa: E402
from app.core.config import DemoMode, settings  # noqa: E402
from app.core.db import create_all, session_scope  # noqa: E402
from app.core.enums import GraphStatus, ItemType  # noqa: E402
from app.core.llm import build_provider  # noqa: E402
from app.core.llm_runner import LLMRunner  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.competency import CompetencyGraph  # noqa: E402
from app.models.ontology import Job, Skill  # noqa: E402
from app.models.student import AssessmentItem, AssessmentItemSkill  # noqa: E402
from app.services.competency_graph_service import CompetencyGraphService  # noqa: E402
from app.services.skill_normalizer import SkillNormalizer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="生成诊断测评题库")
    parser.add_argument("--job", default="ai_data_annotator")
    parser.add_argument("--per-skill", type=int, default=4, help="每个技能出几题")
    parser.add_argument("--batch", type=int, default=2, help="每次调用覆盖几个技能")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging("WARNING")
    create_all()

    if not settings.llm_api_key:
        print("❌ 未配置 LLM_API_KEY")
        return 1

    agent = AssessmentItemAgent(
        runner=LLMRunner(provider=build_provider(), demo_mode=DemoMode.RECORD)
    )
    created = 0
    rejected: list[tuple[str, str]] = []

    with session_scope() as db:
        job = db.get(Job, args.job)
        if job is None:
            print(f"❌ 未找到岗位：{args.job}")
            return 1

        graph = db.execute(
            select(CompetencyGraph).where(
                CompetencyGraph.job_id == args.job,
                CompetencyGraph.status == GraphStatus.APPROVED,
            )
        ).scalars().first()
        if graph is None:
            print(f"❌ 岗位 {args.job} 尚无已审核图谱，无法确定要考查哪些技能")
            return 1

        target = CompetencyGraphService(db).target_skill_vector(graph)
        skills = []
        for code in sorted(target):
            skill = db.get(Skill, code)
            if skill:
                skills.append((code, skill.name_zh, skill.description))

        print(f"岗位：{job.name}")
        print(f"目标能力向量：{len(skills)} 个技能，每个出 {args.per_skill} 题")
        print(f"预计生成 {len(skills) * args.per_skill} 题\n")

        normalizer = SkillNormalizer(db)

        # 按 batch 分组出题：一次给模型几个相关技能，比逐个出题更省调用
        for start in range(0, len(skills), args.batch):
            group = skills[start : start + args.batch]
            names = "、".join(name for _, name, _ in group)
            envelope = agent.run(
                db,
                ItemGenerationInput(
                    skills=group,
                    count=args.per_skill * len(group),
                    job_name=job.name,
                ),
            )

            accepted = 0
            for item in envelope.result.items:
                # 闸门：技能编码必须解析到技能表，否则该题无法归因
                resolved = normalizer.resolve(item.skill_code)
                if resolved is None:
                    rejected.append((item.stem[:24], f"技能 {item.skill_code} 不存在"))
                    continue
                # 闸门：选择题必须有选项，判断题必须没有
                if item.item_type in (ItemType.SINGLE, ItemType.MULTI) and not item.options:
                    rejected.append((item.stem[:24], "选择题缺少选项"))
                    continue
                # 闸门：答案必须落在选项内
                if item.options:
                    keys = {o.key for o in item.options}
                    if not set(item.answer_key) <= keys:
                        rejected.append((item.stem[:24], "答案不在选项中"))
                        continue

                if args.dry_run:
                    accepted += 1
                    continue

                record = AssessmentItem(
                    id=f"item_{uuid.uuid4().hex[:14]}",
                    job_id=args.job,
                    stem=item.stem,
                    item_type=item.item_type,
                    options=[o.model_dump() for o in item.options],
                    answer_key=list(item.answer_key),
                    explanation=item.explanation,
                    difficulty=item.difficulty,
                    source_ref=[
                        {
                            "chunk_id": s.chunk_id,
                            "source_name": s.source_name,
                            "page": s.page,
                            "quote": s.quote,
                        }
                        for s in envelope.sources
                        if s.marker in item.evidence_markers
                    ],
                    generation_run_id=envelope.llm_run_id,
                )
                db.add(record)
                db.flush()
                db.add(
                    AssessmentItemSkill(
                        item_id=record.id, skill_code=resolved, weight=1.0
                    )
                )
                accepted += 1
                created += 1

            print(f"  {names[:34]:36s} 采纳 {accepted:2d}  累计 {created}")

        if not args.dry_run:
            db.flush()

    print(f"\n{'预览' if args.dry_run else '入库'} {created} 题")
    if rejected:
        print(f"\n⚠️  丢弃 {len(rejected)} 题：")
        for stem, reason in rejected[:10]:
            print(f"     {stem}… — {reason}")

    if not args.dry_run:
        with session_scope() as db:
            from sqlalchemy import func

            rows = db.execute(
                select(AssessmentItemSkill.skill_code, func.count())
                .group_by(AssessmentItemSkill.skill_code)
                .order_by(func.count())
            ).all()
            thin = [(c, n) for c, n in rows if n < 3]
            print(f"\n题库覆盖 {len(rows)} 个技能")
            if thin:
                print("⚠️  以下技能题量不足 3 题，其能力估计不可信：")
                for code, count in thin:
                    print(f"     {code:32s} {count} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
