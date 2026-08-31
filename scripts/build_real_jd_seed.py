"""由已核验的原始捕获批次生成正式 JD 种子文件。

本脚本不抓取网络，也不改写 ``raw_text``；只做可复现的合并、排除与 JSON 输出。
运行：
    python scripts/build_real_jd_seed.py --check
    python scripts/build_real_jd_seed.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "seed" / "job_postings_ai_data_annotator.json"

# 该看板的统计口径是「国内 AI 数据标注岗位族（初级/实习/专项/质检）」。
# 组长管理岗、高级算法研发岗、海外岗位仍保存在原始捕获区，用于后续画像对比，
# 但不应混入第一阶段学生目标岗位的技能需求频率。
EXCLUDED_IDS = {
    "real_jd_024",  # 数据标注员组长：管理岗
    "real_jd_029",  # 数据标注算法工程师：高级算法研发岗
    "real_jd_030",  # Data Annotator：海外岗位
}


def build_payload() -> tuple[dict, list[str]]:
    entries: list[dict] = []
    input_files: list[str] = []
    seen: set[str] = set()

    for path in sorted(RAW_DIR.glob("jd_capture_batch_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        input_files.append(path.name)
        for entry in payload.get("postings", []):
            posting_id = str(entry.get("id", ""))
            if not posting_id:
                raise ValueError(f"{path.name} 存在缺少 id 的记录")
            if posting_id in seen:
                raise ValueError(f"跨批次重复 id：{posting_id}")
            seen.add(posting_id)
            if posting_id not in EXCLUDED_IDS:
                entries.append(entry)

    if len(entries) != 30:
        raise ValueError(f"核心统计样本应为 30 条，当前得到 {len(entries)} 条")
    if any(entry.get("data_flag") != "REAL" for entry in entries):
        raise ValueError("核心统计样本中存在非 REAL 记录")
    if any(not entry.get("source_url") for entry in entries):
        raise ValueError("核心统计样本中存在缺少 source_url 的记录")

    return (
        {
            "_status": "REAL JD 正式种子；由原始捕获批次机械合并，尚未执行数据库导入。",
            "sample_scope": {
                "name": "国内 AI 数据标注岗位族（初级/实习/专项/质检）",
                "included_count": len(entries),
                "excluded_ids": sorted(EXCLUDED_IDS),
                "exclusion_reason": "排除管理岗、高级算法研发岗与海外岗位，避免与第一阶段学生目标岗位混合统计。",
            },
            "job_id": "ai_data_annotator",
            "postings": entries,
        },
        input_files,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="构建正式 REAL JD 种子文件")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="仅检查，不写文件")
    mode.add_argument("--write", action="store_true", help="生成正式种子文件")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payload, input_files = build_payload()
    print(f"已读取 {len(input_files)} 个捕获批次，核心 REAL 样本 {len(payload['postings'])} 条")
    print("排除：" + ", ".join(payload["sample_scope"]["excluded_ids"]))

    if args.check:
        print("（--check，未写文件）")
        return 0

    output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已生成：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
