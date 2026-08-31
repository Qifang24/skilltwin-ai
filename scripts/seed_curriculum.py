"""导入带原文证据的课程方案节选。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.db import create_all, session_scope  # noqa: E402
from app.models.curriculum import CourseSkillCoverage, CurriculumCourse, CurriculumPlan  # noqa: E402
from app.models.knowledge import KnowledgeChunk  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "seed" / "curriculum_hnjd_2023.json"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _validate_evidence(db, payload: dict) -> list[str]:
    """保证课程与映射的引用均能回到已入库知识块的原文。"""
    errors: list[str] = []
    seen_course_ids: set[str] = set()
    course_ids: set[str] = set()

    for row in payload["courses"]:
        course_id = row["id"]
        if course_id in seen_course_ids:
            errors.append(f"重复 course id：{course_id}")
        seen_course_ids.add(course_id)
        course_ids.add(course_id)
        chunk = db.get(KnowledgeChunk, row["source_chunk_id"])
        if chunk is None:
            errors.append(f"课程 {course_id} 的来源块不存在：{row['source_chunk_id']}")
        elif _compact(row["source_quote"]) not in _compact(chunk.text):
            errors.append(f"课程 {course_id} 的 source_quote 不在来源块原文中")

    seen_pairs: set[tuple[str, str]] = set()
    for row in payload["coverage"]:
        pair = (row["course_id"], row["skill_code"])
        if pair in seen_pairs:
            errors.append(f"重复课程技能映射：{pair[0]} → {pair[1]}")
        seen_pairs.add(pair)
        if row["course_id"] not in course_ids:
            errors.append(f"映射引用了不存在的课程：{row['course_id']}")
        chunk = db.get(KnowledgeChunk, row["source_chunk_id"])
        if chunk is None:
            errors.append(f"映射 {pair[0]} → {pair[1]} 的来源块不存在：{row['source_chunk_id']}")
        elif _compact(row["evidence_quote"]) not in _compact(chunk.text):
            errors.append(f"映射 {pair[0]} → {pair[1]} 的 evidence_quote 不在来源块原文中")
    return errors


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="导入带原文证据的课程方案节选")
    parser.add_argument(
        "--file",
        help="课程方案 JSON 文件；相对路径按项目根目录解析，默认导入当前公共样例",
    )
    parser.add_argument("--check", action="store_true", help="仅验证引用证据，不写数据库")
    args = parser.parse_args()

    path = Path(args.file) if args.file else DEFAULT_INPUT
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if not path.exists():
        parser.error(f"找不到课程方案文件：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    create_all()
    with session_scope() as db:
        errors = _validate_evidence(db, payload)
        if errors:
            print(f"证据校验失败：{len(errors)} 项")
            for error in errors:
                print(f"- {error}")
            return 1
        if args.check:
            print(
                f"证据校验通过：{len(payload['courses'])} 门课程、"
                f"{len(payload['coverage'])} 条技能映射。（--check，未写库）"
            )
            return 0
        plan_data = payload["plan"]
        plan = db.get(CurriculumPlan, plan_data["id"])
        if plan is None:
            plan = CurriculumPlan(**plan_data)
            db.add(plan)
        else:
            for key, value in plan_data.items():
                setattr(plan, key, value)
        db.flush()
        for row in payload["courses"]:
            item = db.get(CurriculumCourse, row["id"])
            if item is None:
                db.add(CurriculumCourse(plan_id=plan.id, **row))
            else:
                for key, value in row.items():
                    setattr(item, key, value)
        db.flush()
        for row in payload["coverage"]:
            item = db.query(CourseSkillCoverage).filter_by(course_id=row["course_id"], skill_code=row["skill_code"]).one_or_none()
            if item is None:
                db.add(CourseSkillCoverage(**row))
            else:
                for key, value in row.items():
                    setattr(item, key, value)
    print(f"已导入 {path.name}：{len(payload['courses'])} 门课程、{len(payload['coverage'])} 条有原文证据的技能映射")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
