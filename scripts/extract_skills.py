"""从职业标准原文抽取规范技能表 → data/seed/skills_<job>.json

    python scripts/extract_skills.py --doc doc_ai_trainer_std_2021
    python scripts/extract_skills.py --dry-run        # 不写文件

核心是**引文核验**：模型给出的 evidence_quote 必须能在来源 chunk 原文中
一字不差地找到（忽略空白差异），否则该候选直接丢弃。
这让「编造一个标准里根本没有的技能」在机制上无法通过 —— 模型可以幻觉出
技能名，但编不出对应的原文。

产出的 seed 文件 provenance 一律标 llm_drafted：
真教师签字前，不允许冒充 human_reviewed。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agents.skill_extraction import (  # noqa: E402
    SkillExtractionAgent,
    SkillExtractionInput,
)
from app.core.config import DemoMode, settings  # noqa: E402
from app.core.db import create_all, session_scope  # noqa: E402
from app.core.llm import build_provider  # noqa: E402
from app.core.llm_runner import LLMRunner  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc  # noqa: E402
from app.schemas.skill import ExtractedSkill  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = PROJECT_ROOT / "data" / "seed"
OVERRIDES = PROJECT_ROOT / "knowledge" / "skill_overrides.json"

_WS = re.compile(r"\s+")

#: 无信息量的技能名。允许它们进表等于给能力向量塞进无法测评的维度。
_VAGUE_TOKENS = {
    "general", "basic", "common", "misc", "other", "various",
    "labeling", "annotation", "data", "system", "management", "knowledge",
}

#: 高职毕业生的入职岗位对应国标五级/初级工与四级/中级工。
#: 三级及以上属职业晋升路径（带徒培训、系统设计、业务规划），
#: 纳入入门技能表只会让能力向量塞满学生根本不需要测评的维度。
#:
#: 必须匹配**章节编号**而非裸提及：标准的「说明」页有一句
#: 「分为五级/初级工、四级/中级工、三级/高级工、二级/技师、一级/高级技师五个等级」，
#: 只按关键词匹配会在第 3 块就误截断。
_LEVEL_CUTOFF_RE = re.compile(r"3\.\d\s*三级/高级工")
_LEVEL_CUTOFF_DESC = "3.3 三级/高级工"


def _normalise_for_match(text: str) -> str:
    """比对用归一：去掉所有空白。

    只容忍空白差异（PDF 抽取的空格位置本就不可靠），
    不容忍字符差异 —— 那才是编造与引用的分界线。
    """
    return _WS.sub("", text)


def _quote_is_verifiable(quote: str, source_text: str) -> bool:
    return _normalise_for_match(quote) in _normalise_for_match(source_text)


def _section_for_quote(quote: str, chunk_text: str, fallback: str | None) -> str | None:
    """定位引文所在的**章节**，而非该块的起始章节。

    知识块常跨章节：一块可能从「1.9 职业技能鉴定要求」开始，正文却延伸到
    「2.1 职业道德」。若沿用块级章节标签，引用会把读者指向错误的条文。
    这里在块内回溯到引文之前最近的标题行。
    """
    from app.rag.chunker import _is_heading

    target = _normalise_for_match(quote)
    normalised_prefix = ""
    section = fallback

    for line in chunk_text.splitlines():
        heading = _is_heading(line)
        if heading:
            section = heading
        normalised_prefix += _normalise_for_match(line)
        if target and target in normalised_prefix:
            return section
    return section


def _name_is_vague(skill_code: str) -> bool:
    """技能名的最后一段若是空泛词，视为不可测评。"""
    tail = skill_code.split(".", 1)[1] if "." in skill_code else skill_code
    return tail in _VAGUE_TOKENS


def _apply_overrides(merged: OrderedDict[str, dict]) -> list[str]:
    """按书写顺序应用人工策展规则，返回操作日志。

    顺序有意义：先 rename 腾出编码，再 merge，最后 rename 定名。
    合并时保留 from 的全部来源引用与别名 —— 策展是为了消重，不是为了丢证据。
    """
    if not OVERRIDES.exists():
        return []

    config = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    log: list[str] = []

    for rule in config.get("rules", []):
        kind = rule.get("type")

        if kind == "rename":
            old, new = rule["from"], rule["to"]
            if old not in merged:
                continue
            if new in merged and new != old:
                log.append(f"⚠️  重命名 {old} → {new}（目标已存在，跳过）")
                continue
            entry = merged.pop(old)
            entry["skill_code"] = new
            for field in ("category", "name_zh", "name_en", "description"):
                if field in rule:
                    entry[field] = rule[field]
            merged[new] = entry
            log.append(f"重命名  {old} → {new}")

        elif kind == "merge":
            source_code, target_code = rule["from"], rule["into"]
            if source_code not in merged:
                continue
            if target_code not in merged:
                log.append(f"⚠️  合并 {source_code} → {target_code}（目标不存在，跳过）")
                continue
            source = merged.pop(source_code)
            target = merged[target_code]
            target["sources"].extend(source["sources"])
            for alias in [source["name_zh"], *source["aliases"]]:
                if alias and alias not in target["aliases"]:
                    target["aliases"].append(alias)
            log.append(f"合并    {source_code} → {target_code}")

        elif kind == "exclude":
            code = rule["skill_code"]
            if merged.pop(code, None) is not None:
                log.append(f"排除    {code}")

    return log


def _cut_at_level(chunks: list) -> list:
    """截断到晋升等级章节出现之前。找不到截断点则全量返回。"""
    for index, chunk in enumerate(chunks):
        if _LEVEL_CUTOFF_RE.search(_normalise_for_match(chunk.text)):
            return chunks[:index]
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="从标准原文抽取规范技能表")
    parser.add_argument("--doc", default="doc_ai_trainer_std_2021", help="来源文档 id")
    parser.add_argument("--job", default="ai_data_annotator", help="岗位 slug")
    parser.add_argument("--dry-run", action="store_true", help="不写 seed 文件")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 块（调试用）")
    parser.add_argument(
        "--levels",
        choices=["entry", "all"],
        default="entry",
        help="entry=仅五级/四级（高职入职层，默认）；all=全部五个等级",
    )
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging("WARNING")
    create_all()

    if not settings.llm_api_key:
        print("❌ 未配置 LLM_API_KEY，无法调用模型抽取。")
        return 1

    # RECORD 模式：重复运行命中缓存，不重复烧 token
    agent = SkillExtractionAgent(
        runner=LLMRunner(provider=build_provider(), demo_mode=DemoMode.RECORD)
    )

    merged: OrderedDict[str, dict] = OrderedDict()
    rejected: list[tuple[str, str, str]] = []  # (chunk_id, skill_code, 原因)
    processed = 0

    with session_scope() as db:
        doc = db.get(KnowledgeDoc, args.doc)
        if doc is None:
            print(f"❌ 找不到文档 {args.doc}，请先运行 ingest_knowledge.py")
            return 1

        chunks = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.doc_id == args.doc)
            .order_by(KnowledgeChunk.chunk_index)
            .all()
        )
        total_chunks = len(chunks)
        if args.levels == "entry":
            chunks = _cut_at_level(chunks)
        if args.limit:
            chunks = chunks[: args.limit]

        print(f"来源：《{doc.title}》")
        print(f"标准号：{doc.standard_id or '（无）'}")
        if args.levels == "entry":
            print(
                f"等级范围：五级/初级工 + 四级/中级工（高职入职层）"
                f" —— 截断于「{_LEVEL_CUTOFF_DESC}」之前"
            )
        else:
            print("等级范围：全部五个等级")
        print(f"待处理 {len(chunks)} / {total_chunks} 个知识块\n")

        for chunk in chunks:
            envelope = agent.run(
                db,
                SkillExtractionInput(
                    chunk_id=chunk.id,
                    chunk_text=chunk.text,
                    page=chunk.page,
                    section=chunk.section,
                ),
            )
            processed += 1
            accepted_here = 0

            for skill in envelope.result.skills:
                # ---- 闸门 1：引文必须真的出自原文 ----
                if not _quote_is_verifiable(skill.evidence_quote, chunk.text):
                    rejected.append((chunk.id, skill.skill_code, "引文未见于原文"))
                    continue
                # ---- 闸门 2：前缀与 category 必须自洽 ----
                if not skill.prefix_matches_category():
                    rejected.append(
                        (chunk.id, skill.skill_code, f"前缀与 category({skill.category.value}) 不符")
                    )
                    continue
                # ---- 闸门 3：名称必须具体到可测评 ----
                if _name_is_vague(skill.skill_code):
                    rejected.append((chunk.id, skill.skill_code, "名称空泛，无法测评"))
                    continue

                source = {
                    "chunk_id": chunk.id,
                    "page": chunk.page,
                    # 用引文所在章节，而非块的起始章节 —— 块常跨章节
                    "section": _section_for_quote(
                        skill.evidence_quote, chunk.text, chunk.section
                    ),
                    "quote": skill.evidence_quote,
                }
                if skill.skill_code in merged:
                    entry = merged[skill.skill_code]
                    entry["sources"].append(source)
                    for alias in skill.aliases:
                        if alias not in entry["aliases"]:
                            entry["aliases"].append(alias)
                else:
                    merged[skill.skill_code] = {
                        "skill_code": skill.skill_code,
                        "name_zh": skill.name_zh,
                        "name_en": skill.name_en,
                        "category": skill.category.value,
                        "description": skill.description,
                        "aliases": list(skill.aliases),
                        "provenance": "llm_drafted",
                        "sources": [source],
                    }
                accepted_here += 1

            marker = "·" if accepted_here else " "
            print(
                f"  {marker} 块#{chunk.chunk_index:<3} 第{str(chunk.page or '?'):>2}页  "
                f"采纳 {accepted_here}  累计 {len(merged)}"
            )

    raw_count = len(merged)
    override_log = _apply_overrides(merged)

    print(f"\n处理 {processed} 块，模型产出 {raw_count} 个技能点")
    if override_log:
        print("人工策展（knowledge/skill_overrides.json）：")
        for line in override_log:
            print(f"     {line}")
        print(f"策展后剩余 {len(merged)} 个")
    if rejected:
        print(f"\n⚠️  丢弃 {len(rejected)} 条未通过核验的候选：")
        for chunk_id, code, reason in rejected[:15]:
            print(f"     {code:32s} {reason}   ({chunk_id})")
        if len(rejected) > 15:
            print(f"     …另有 {len(rejected) - 15} 条")

    by_category: dict[str, list[str]] = {}
    for entry in merged.values():
        by_category.setdefault(entry["category"], []).append(entry["skill_code"])
    print("\n按类别分布：")
    for category, codes in sorted(by_category.items()):
        print(f"  {category:12s} {len(codes):2d}  {', '.join(sorted(codes))}")

    if args.dry_run:
        print("\n（--dry-run，未写文件）")
        return 0

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SEED_DIR / f"skills_{args.job}.json"
    payload = {
        "_comment": [
            "由 scripts/extract_skills.py 从职业标准原文抽取生成。",
            "每条技能的 sources[].quote 均已通过程序核验：",
            "必须是来源 chunk 原文中一字不差的连续片段（忽略空白差异）。",
            "provenance = llm_drafted —— 尚未经真实教师审核，勿标为 human_reviewed。",
        ],
        "job": args.job,
        "source_doc_id": args.doc,
        "skills": list(merged.values()),
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已写入 {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
