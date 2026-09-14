"""Initialize a Vercel Marketplace Postgres database from the local repo.

Run with ``vercel env run -e production -- .venv/bin/python
scripts/bootstrap_vercel.py``. The CLI cannot reveal Sensitive project variables
locally and represents them as placeholders, so this runner removes those values
before importing application settings. The Marketplace DATABASE_URL remains
available; for OpenRouter index builds, pass EMBEDDING_API_KEY temporarily.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 Vercel 托管 Postgres")
    parser.add_argument("--skip-index", action="store_true", help="暂时只启用数据库 BM25 检索")
    parser.add_argument("--step", choices=("all", "migrate", "skills", "postings", "knowledge", "index", "curriculum"), default="all")
    args = parser.parse_args()
    env = {key: value for key, value in os.environ.items() if value and value != "[SENSITIVE]"}
    if not env.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        print("缺少 Vercel Marketplace 提供的 PostgreSQL DATABASE_URL。", file=sys.stderr)
        return 1
    embedding_base_url = env.get("EMBEDDING_BASE_URL", "https://ai-gateway.vercel.sh/v1").rstrip("/")
    if args.step in ("all", "index") and not args.skip_index:
        if embedding_base_url == "https://ai-gateway.vercel.sh/v1":
            credential_present = bool(env.get("EMBEDDING_API_KEY") or env.get("AI_GATEWAY_API_KEY") or env.get("VERCEL_OIDC_TOKEN"))
        else:
            credential_present = bool(env.get("EMBEDDING_API_KEY") or env.get("LLM_API_KEY"))
        if not credential_present:
            print("缺少 embedding 服务凭证；本地构建索引请临时提供 EMBEDDING_API_KEY。", file=sys.stderr)
            return 1

    env.update({
        "VERCEL": "1",
        "VECTOR_STORE": "sql",
        "FILE_STORAGE": "database",
        "EMBEDDING_PROVIDER": "openai_compat",
    })
    env.setdefault("EMBEDDING_BASE_URL", embedding_base_url)
    env.setdefault("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    env.setdefault("EMBEDDING_DIM", "1536")
    py = sys.executable
    jobs = [
        ("migrate", "数据库迁移", [py, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"]),
        ("skills", "技能种子", [py, "scripts/seed_skills.py"]),
        ("postings", "岗位样例", [py, "scripts/import_postings.py", "--file", "data/seed/job_postings_ai_data_annotator.json"]),
        ("knowledge", "知识来源", [py, "scripts/ingest_knowledge.py"]),
        ("index", "检索索引", [py, "scripts/build_index.py"]),
        ("curriculum", "课程样例", [py, "scripts/seed_curriculum.py"]),
    ]
    for step, label, command in jobs:
        if (args.step != "all" and step != args.step) or (args.skip_index and step == "index"):
            continue
        print(f"\n=== {label} ===", flush=True)
        job_env = env.copy()
        if step == "migrate" and env.get("DATABASE_URL_UNPOOLED"):
            job_env["DATABASE_URL"] = env["DATABASE_URL_UNPOOLED"]
        result = subprocess.run(command, cwd=ROOT, env=job_env, check=False)
        if result.returncode:
            print(f"{label}失败（退出码 {result.returncode}）。", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
