"""重建数据库（MVP 阶段替代 Alembic）。

    python scripts/reset_db.py            # 建表（已存在的不动）
    python scripts/reset_db.py --drop     # 先删后建，清空所有数据

schema 稳定后再引入 Alembic；当前阶段迁移文件的维护成本大于收益。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本能直接以 `python scripts/reset_db.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.db import create_all, drop_all, engine  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="重建 SkillTwin AI 数据库")
    parser.add_argument(
        "--drop", action="store_true", help="先删除所有表（会清空全部数据）"
    )
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging(settings.log_level)

    print(f"目标数据库：{settings.database_url}")

    if args.drop:
        if not args.yes:
            answer = input("这会删除所有表及其数据，确认继续？输入 yes 继续：").strip()
            if answer != "yes":
                print("已取消。")
                return 1
        drop_all()
        print("已删除所有表。")

    create_all()

    from sqlalchemy import inspect

    tables = sorted(inspect(engine).get_table_names())
    print(f"建表完成，共 {len(tables)} 张：")
    for name in tables:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
