"""把技能种子文件写入 skill 表。

    python scripts/seed_skills.py                    # 载入全部 seed 文件
    python scripts/seed_skills.py --file data/seed/skills_ai_data_annotator.json
    python scripts/seed_skills.py --check            # 只校验，不写库

写入后会立即用 SkillNormalizer 自检：
若存在归一化后撞车的别名（两个技能声称同一个写法），直接报错退出 ——
那意味着 join key 有歧义，放任不管会让下游统计静默出错。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.db import create_all, session_scope  # noqa: E402
from app.core.enums import Provenance, SkillCategory, SkillStatus  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.ontology import Skill  # noqa: E402
from app.services.skill_normalizer import SkillNormalizer  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = PROJECT_ROOT / "data" / "seed"


def _load(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("skills", [])


def main() -> int:
    parser = argparse.ArgumentParser(description="载入技能种子数据")
    parser.add_argument("--file", help="指定单个 seed 文件；默认载入 data/seed/skills_*.json")
    parser.add_argument("--check", action="store_true", help="只校验，不写库")
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging("WARNING")
    create_all()

    if args.file:
        requested = Path(args.file)
        files = [requested if requested.is_absolute() else PROJECT_ROOT / requested]
    else:
        files = sorted(SEED_DIR.glob("skills_*.json"))
    if not files:
        print(f"❌ 未找到种子文件（{SEED_DIR}/skills_*.json）")
        print("   请先运行 scripts/extract_skills.py 生成")
        return 1

    entries: list[dict] = []
    for path in files:
        loaded = _load(path)
        print(f"读取 {path.relative_to(PROJECT_ROOT)}：{len(loaded)} 条")
        entries.extend(loaded)

    # 文件内查重
    codes = [e["skill_code"] for e in entries]
    duplicates = {c for c in codes if codes.count(c) > 1}
    if duplicates:
        print(f"❌ 种子文件内存在重复 skill_code：{sorted(duplicates)}")
        return 1

    if args.check:
        print(f"\n校验通过：{len(entries)} 条技能，无重复编码。（--check，未写库）")
        return 0

    created = updated = 0
    with session_scope() as db:
        for entry in entries:
            skill = db.get(Skill, entry["skill_code"])
            fields = dict(
                name_zh=entry["name_zh"],
                name_en=entry.get("name_en"),
                category=SkillCategory(entry["category"]),
                description=entry.get("description"),
                aliases=list(entry.get("aliases", [])),
                evidence=list(entry.get("sources", [])),
                status=SkillStatus.ACTIVE,
                provenance=Provenance(entry.get("provenance", "llm_drafted")),
            )
            if skill is None:
                db.add(Skill(skill_code=entry["skill_code"], **fields))
                created += 1
            else:
                for key, value in fields.items():
                    setattr(skill, key, value)
                updated += 1

    print(f"\n入库完成：新建 {created}，更新 {updated}")

    # ---- 自检：归一化后不得有撞车别名 ----
    with session_scope() as db:
        normalizer = SkillNormalizer(db)
        print(f"技能表现有 {normalizer.size} 条 active 技能")

        if normalizer.ambiguous_aliases:
            print("\n❌ 存在归一化后撞车的别名 —— join key 有歧义，必须消歧：")
            for key, owners in normalizer.ambiguous_aliases.items():
                print(f"     「{key}」被这些技能同时声称：{owners}")
            return 1
        print("自检通过：无歧义别名")

        # 抽样展示归一化效果
        samples = ["数据清洗", "data.cleaning", "Data  Cleaning", "图像标注", "不存在的技能"]
        print("\n归一化抽样：")
        for match in normalizer.normalize_many(samples):
            target = f"{match.skill_code} ({match.name_zh})" if match.is_matched else "—"
            print(f"     {match.term:16s} → {target:34s} [{match.matched_by}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
