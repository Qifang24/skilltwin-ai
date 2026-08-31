"""导入岗位数据 → job_posting 表。

    python scripts/import_postings.py --file data/seed/job_postings_ai_data_annotator.json
    python scripts/import_postings.py --file <文件> --check   # 只校验不写库

校验从严、报错要具体：填 40 条 JD 是件枯燥的体力活，
错误信息必须直接说清「第几条、哪个字段、怎么改」，不能让人自己猜。

导入时自动脱敏联系方式（手机号 / 邮箱 / 微信号 / QQ）——
项目合规要求不存储未脱敏的个人信息。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.db import create_all, session_scope  # noqa: E402
from app.core.enums import DataFlag  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.job_market import JobPosting  # noqa: E402
from app.models.ontology import Job  # noqa: E402
from app.services.job_market_service import JobMarketService  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 模板里的占位文字，出现即说明该条没真填
_PLACEHOLDER_HINTS = ("【", "…（", "把岗位描述", "第二条 JD")

_PII_PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "[手机号已脱敏]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[邮箱已脱敏]"),
    (re.compile(r"(微信|weixin|wechat|VX|vx)[:：\s]*[A-Za-z0-9_-]{5,}"), "[微信号已脱敏]"),
    (re.compile(r"\bQQ[:：\s]*\d{5,}", re.IGNORECASE), "[QQ号已脱敏]"),
]


def scrub_pii(text: str) -> tuple[str, bool]:
    """抹去联系方式。返回 (处理后文本, 是否发生替换)。"""
    scrubbed = text
    for pattern, replacement in _PII_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed, scrubbed != text


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _validate(entry: dict, index: int, seen_ids: set[str]) -> list[str]:
    """返回该条目的全部问题。一次报全，避免让人反复试错。"""
    label = f"第 {index + 1} 条"
    problems: list[str] = []

    for field in ("id", "title", "raw_text"):
        if not str(entry.get(field, "")).strip():
            problems.append(f"{label}：缺少必填字段 `{field}`")

    posting_id = str(entry.get("id", "")).strip()
    if posting_id and posting_id in seen_ids:
        problems.append(f"{label}：id `{posting_id}` 与前面重复")

    raw_text = str(entry.get("raw_text", ""))
    if any(hint in raw_text for hint in _PLACEHOLDER_HINTS):
        problems.append(
            f"{label}：raw_text 仍是模板占位文字，请粘贴真实岗位描述原文"
        )
    elif 0 < len(raw_text.strip()) < 40:
        problems.append(
            f"{label}：raw_text 只有 {len(raw_text.strip())} 字，"
            f"疑似只填了关键词。请粘贴完整的岗位职责与任职要求原文 —— "
            f"技能证据要从原文里定位，概括过的文本无法支撑引用"
        )

    flag = str(entry.get("data_flag", "")).strip()
    if flag and flag not in (DataFlag.REAL.value, DataFlag.DEMO.value):
        problems.append(f"{label}：data_flag 只能是 REAL 或 DEMO，当前是 `{flag}`")

    for field in ("salary_min", "salary_max"):
        value = entry.get(field)
        if value is not None and not isinstance(value, int):
            problems.append(f"{label}：`{field}` 应为整数（元/月），当前是 {value!r}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="导入岗位数据")
    parser.add_argument("--file", required=True, help="JSON 文件路径")
    parser.add_argument("--check", action="store_true", help="只校验，不写库")
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging("WARNING")

    path = Path(args.file)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        print(f"❌ 文件不存在：{path}")
        return 1
    if "TEMPLATE" in path.name:
        print("❌ 这是模板文件。请先另存为去掉 TEMPLATE 的文件名，填入真实数据后再导入。")
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    job_id = payload.get("job_id", "ai_data_annotator")
    entries = payload.get("postings", [])
    if not entries:
        print("❌ postings 数组为空")
        return 1

    # ---------- 校验 ----------
    problems: list[str] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        problems.extend(_validate(entry, index, seen_ids))
        if entry.get("id"):
            seen_ids.add(str(entry["id"]).strip())

    if problems:
        print(f"❌ 发现 {len(problems)} 个问题，全部修正后再导入：\n")
        for problem in problems:
            print(f"   • {problem}")
        return 1

    real = sum(1 for e in entries if e.get("data_flag", "DEMO") == "REAL")
    demo = len(entries) - real
    print(f"校验通过：{len(entries)} 条（真实 {real}，演示 {demo}）")

    if args.check:
        print("（--check，未写库）")
        return 0

    # ---------- 写库 ----------
    create_all()
    default_source = payload.get("default_source_name")
    default_license = payload.get("default_license_note")
    created = updated = scrubbed_count = 0

    with session_scope() as db:
        if db.get(Job, job_id) is None:
            db.add(Job(id=job_id, name=payload.get("job_name", job_id)))
            db.flush()
            print(f"已创建岗位记录：{job_id}")

        for entry in entries:
            raw_text, was_scrubbed = scrub_pii(str(entry["raw_text"]))
            if was_scrubbed:
                scrubbed_count += 1

            fields = dict(
                job_id=job_id,
                title=str(entry["title"]).strip(),
                company_type=entry.get("company_type"),
                city=entry.get("city"),
                salary_min=entry.get("salary_min"),
                salary_max=entry.get("salary_max"),
                salary_text=entry.get("salary_text"),
                education_req=entry.get("education_req"),
                experience_req=entry.get("experience_req"),
                raw_text=raw_text,
                source_name=entry.get("source_name") or default_source,
                source_url=entry.get("source_url"),
                license_note=entry.get("license_note") or default_license,
                posted_at=_parse_date(entry.get("posted_at")),
                collected_at=datetime.now(timezone.utc),
                data_flag=DataFlag(entry.get("data_flag", "DEMO")),
                pii_scrubbed=was_scrubbed,
            )

            posting_id = str(entry["id"]).strip()
            existing = db.get(JobPosting, posting_id)
            if existing is None:
                db.add(JobPosting(id=posting_id, **fields))
                created += 1
            else:
                for key, value in fields.items():
                    setattr(existing, key, value)
                updated += 1

    print(f"\n入库完成：新建 {created}，更新 {updated}")
    if scrubbed_count:
        print(f"已对 {scrubbed_count} 条记录脱敏联系方式")

    # 导入后的排名与趋势必须由当前 JD 原文重新计算，不能继续展示旧快照。
    # 该步骤只做确定性别名匹配与 SQL 聚合，不调用 LLM。
    with session_scope() as db:
        analysis = JobMarketService(db).analyze(job_id)
        print(
            "已重建岗位技能统计："
            f"原文技能命中 {analysis.extracted_skill_links} 条，"
            f"写入快照 {analysis.snapshots_written} 条"
        )
        for warning in analysis.dashboard.data_quality.warnings:
            print(f"提示：{warning}")

    with session_scope() as db:
        total = db.query(JobPosting).filter(JobPosting.job_id == job_id).count()
        real_total = (
            db.query(JobPosting)
            .filter(JobPosting.job_id == job_id, JobPosting.data_flag == DataFlag.REAL)
            .count()
        )
        print(f"岗位库现有 {total} 条（真实 {real_total}，演示 {total - real_total}）")
        if real_total < 30:
            print(
                f"\n提示：真实样本 {real_total} 条。建议至少 30 条再做需求分析，"
                f"否则百分比的统计意义有限 —— 图表会如实标注样本量 N。"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
