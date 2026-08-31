"""导出待教师审核的技能证据包。

示例：
    .venv\Scripts\python.exe scripts\export_skill_review_packet.py
    .venv\Scripts\python.exe scripts\export_skill_review_packet.py --check

脚本只读取技能 seed 与知识库来源清单，不会改动技能状态或 provenance。
导出的 CSV 以「一条技能 × 一条原文证据」为一行，便于教师逐项核对。
真实教师完成审核前，任何条目都必须保持 ``llm_drafted``。
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = PROJECT_ROOT / "data" / "seed" / "skills_ai_data_annotator.json"
DEFAULT_MANIFEST = PROJECT_ROOT / "knowledge" / "manifest.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "review" / "skill_review_packet.csv"

FIELDNAMES = [
    "packet_id",
    "generated_at_utc",
    "job_id",
    "skill_code",
    "name_zh",
    "name_en",
    "category",
    "description",
    "aliases",
    "current_provenance",
    "source_doc_id",
    "source_name",
    "standard_id",
    "source_chunk_id",
    "page",
    "section",
    "evidence_quote",
    "review_decision",
    "reviewed_name_zh",
    "reviewed_description",
    "review_notes",
    "reviewer_alias",
    "reviewed_at",
]


def _project_path(value: str | None, default: Path) -> Path:
    if value is None:
        return default
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"文件不存在：{path.relative_to(PROJECT_ROOT)}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 格式错误：{path.relative_to(PROJECT_ROOT)}") from exc


def build_rows(seed: dict[str, Any], manifest: dict[str, Any], packet_id: str, generated_at: str) -> list[dict[str, str]]:
    """校验输入并构造每个技能证据的审核行。"""
    docs = {doc["id"]: doc for doc in manifest.get("documents", []) if doc.get("id")}
    job_id = str(seed.get("job") or "")
    skills = seed.get("skills")
    if not job_id or not isinstance(skills, list) or not skills:
        raise ValueError("技能 seed 缺少 job 或 skills")

    codes: set[str] = set()
    rows: list[dict[str, str]] = []
    for skill in skills:
        code = str(skill.get("skill_code") or "")
        if not code:
            raise ValueError("发现缺少 skill_code 的技能条目")
        if code in codes:
            raise ValueError(f"重复 skill_code：{code}")
        codes.add(code)

        provenance = str(skill.get("provenance") or "")
        if provenance != "llm_drafted":
            raise ValueError(
                f"{code} 的 provenance 为 {provenance!r}；"
                "该导出器仅用于导出尚待审核的 llm_drafted 条目"
            )
        sources = skill.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"{code} 缺少可审核的来源证据")

        for source in sources:
            doc_id = str(source.get("doc_id") or seed.get("source_doc_id") or "")
            doc = docs.get(doc_id)
            if doc is None:
                raise ValueError(f"{code} 引用了未登记的 source_doc_id：{doc_id or '（空）'}")
            quote = str(source.get("quote") or "")
            chunk_id = str(source.get("chunk_id") or "")
            if not quote or not chunk_id:
                raise ValueError(f"{code} 的来源缺少 chunk_id 或 quote")
            rows.append(
                {
                    "packet_id": packet_id,
                    "generated_at_utc": generated_at,
                    "job_id": job_id,
                    "skill_code": code,
                    "name_zh": str(skill.get("name_zh") or ""),
                    "name_en": str(skill.get("name_en") or ""),
                    "category": str(skill.get("category") or ""),
                    "description": str(skill.get("description") or ""),
                    "aliases": " | ".join(str(a) for a in skill.get("aliases", [])),
                    "current_provenance": provenance,
                    "source_doc_id": doc_id,
                    "source_name": str(doc.get("source_name") or doc.get("title") or ""),
                    "standard_id": str(doc.get("standard_id") or ""),
                    "source_chunk_id": chunk_id,
                    "page": str(source.get("page") or ""),
                    "section": str(source.get("section") or ""),
                    "evidence_quote": quote,
                    "review_decision": "",
                    "reviewed_name_zh": "",
                    "reviewed_description": "",
                    "review_notes": "",
                    "reviewer_alias": "",
                    "reviewed_at": "",
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="导出技能表教师审核 CSV")
    parser.add_argument("--seed", help="技能 seed 路径")
    parser.add_argument("--manifest", help="知识库 manifest 路径")
    parser.add_argument("--out", help="导出 CSV 路径")
    parser.add_argument("--check", action="store_true", help="只校验，不导出 CSV")
    args = parser.parse_args()

    seed_path = _project_path(args.seed, DEFAULT_SEED)
    manifest_path = _project_path(args.manifest, DEFAULT_MANIFEST)
    out_path = _project_path(args.out, DEFAULT_OUT)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    packet_id = f"skill-review-{generated_at[:10]}"
    rows = build_rows(_load_json(seed_path), _load_json(manifest_path), packet_id, generated_at)
    skill_count = len({row["skill_code"] for row in rows})
    print(f"校验通过：{skill_count} 项技能，{len(rows)} 条原文证据。")

    if args.check:
        print("（--check，未导出审核包）")
        return 0
    if out_path.exists():
        print(f"未导出：目标文件已存在，避免覆盖真实审核记录：{out_path}")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"已导出：{out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
