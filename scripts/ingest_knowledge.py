"""知识库摄取：原始文档 → knowledge_doc + knowledge_chunk。

    python scripts/ingest_knowledge.py            # 增量（内容未变则跳过）
    python scripts/ingest_knowledge.py --force    # 强制重建
    python scripts/ingest_knowledge.py --dry-run  # 只看会切成什么样，不写库

来源元数据全部取自 knowledge/manifest.json —— 那里的每个字段都经过人工核实。
本脚本不会为任何文档编造标准编号、出版年份或页码：manifest 里是 null 的，
入库后就是 null，引用时该字段直接省略。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import delete, select  # noqa: E402

from app.core.db import create_all, session_scope, utcnow  # noqa: E402
from app.core.enums import SourceType  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc  # noqa: E402
from app.rag.chunker import chunk_pages  # noqa: E402
from app.rag.loader import load_document  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
MANIFEST = KNOWLEDGE_DIR / "manifest.json"


def _content_hash(path: Path, physical_page_range: list[int] | None = None) -> str:
    """Hash both source bytes and the declared ingest scope.

    A large PDF can contain several independent programmes.  Changing the
    selected physical-page range changes the RAG corpus even when the PDF bytes
    do not change, so it must trigger a rebuild rather than silently reusing
    the previous document chunks.
    """
    digest = hashlib.sha256(path.read_bytes())
    digest.update(json.dumps(physical_page_range, ensure_ascii=True).encode("ascii"))
    return digest.hexdigest()[:32]


def _select_pages(pages, entry: dict):
    """Limit an entry to a verified inclusive physical-PDF page range, if set."""
    selected = entry.get("physical_page_range")
    if selected is None:
        return pages
    if (
        not isinstance(selected, list)
        or len(selected) != 2
        or not all(isinstance(value, int) for value in selected)
    ):
        raise ValueError("physical_page_range 必须为两个整数构成的数组，例如 [270, 307]")
    start, end = selected
    if start < 1 or end < start:
        raise ValueError("physical_page_range 必须为有效的递增物理页码范围")
    scoped = [page for page in pages if start <= page.page_index <= end]
    if not scoped:
        raise ValueError(f"physical_page_range [{start}, {end}] 未命中文档任何页面")
    return scoped


def main() -> int:
    parser = argparse.ArgumentParser(description="摄取知识库文档")
    parser.add_argument("--force", action="store_true", help="即使内容未变也重建")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写库")
    args = parser.parse_args()

    force_utf8_stdio()
    setup_logging("WARNING")

    if not MANIFEST.exists():
        print(f"❌ 缺少来源清单：{MANIFEST}")
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["documents"]

    if not args.dry_run:
        create_all()

    total_chunks = 0
    print(f"来源清单共 {len(entries)} 篇文档\n")

    for entry in entries:
        path = KNOWLEDGE_DIR / entry["file"]
        if not path.exists():
            print(f"⚠️  跳过（文件不存在）：{entry['file']}")
            continue

        physical_page_range = entry.get("physical_page_range")
        digest = _content_hash(path, physical_page_range)
        pages = load_document(path)
        try:
            pages = _select_pages(pages, entry)
        except ValueError as exc:
            print(f"❌ {entry['file']} 的摄取范围无效：{exc}")
            return 1
        chunks = chunk_pages(pages)

        pages_with_number = sum(1 for p in pages if p.printed_page)
        chunks_with_page = sum(1 for c in chunks if c.page)

        print(f"《{entry['title']}》")
        print(f"    来源类型   {entry['source_type']}")
        print(f"    标准编号   {entry['standard_id'] or '（无，留空）'}")
        print(f"    页数       {len(pages)}（识别出印刷页码 {pages_with_number} 页）")
        if physical_page_range is not None:
            print(f"    摄取范围   PDF 物理页 {physical_page_range[0]}–{physical_page_range[1]}")
        print(f"    切块       {len(chunks)} 块，其中 {chunks_with_page} 块可定位到页码")

        if args.dry_run:
            sample = next((c for c in chunks if c.page and c.section), None)
            if sample:
                print(f"    样例       [第{sample.page}页 · {sample.section}]")
                print(f"               {sample.text[:80]}…")
            print()
            total_chunks += len(chunks)
            continue

        with session_scope() as db:
            existing = db.get(KnowledgeDoc, entry["id"])
            if existing and existing.content_hash == digest and not args.force:
                print("    → 内容未变，跳过（加 --force 可强制重建）\n")
                total_chunks += len(existing.chunks)
                continue

            if existing:
                db.execute(
                    delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == entry["id"])
                )
                db.delete(existing)
                db.flush()

            doc = KnowledgeDoc(
                id=entry["id"],
                title=entry["title"],
                category=entry.get("category"),
                profession=entry.get("profession"),
                job=entry.get("job"),
                source_name=entry["source_name"],
                source_type=SourceType(entry["source_type"]),
                source_url=entry.get("source_url"),
                publisher=entry.get("publisher"),
                pub_year=entry.get("pub_year"),
                standard_id=entry.get("standard_id"),
                license_note=entry.get("license_note"),
                content_hash=digest,
                ingested_at=utcnow(),
            )
            db.add(doc)
            db.flush()

            for chunk in chunks:
                db.add(
                    KnowledgeChunk(
                        id=f"{entry['id']}#{chunk.index}",
                        doc_id=entry["id"],
                        chunk_index=chunk.index,
                        text=chunk.text,
                        page=chunk.page,
                        section=chunk.section,
                        skill_codes=[],  # Phase 3 建立技能表后回填
                        token_count=chunk.char_count,
                        extra={"page_span": chunk.page_span},
                    )
                )
            print("    → 已入库\n")

        total_chunks += len(chunks)

    print("=" * 60)
    if args.dry_run:
        print(f"预览完成：共将产生 {total_chunks} 个知识块（未写库）")
    else:
        with session_scope() as db:
            docs = db.execute(select(KnowledgeDoc)).scalars().all()
            chunk_total = sum(len(d.chunks) for d in docs)
            with_page = sum(
                1 for d in docs for c in d.chunks if c.page
            )
        print(f"知识库现有 {len(docs)} 篇文档 / {chunk_total} 个知识块")
        print(f"其中 {with_page} 块（{with_page * 100 // max(chunk_total, 1)}%）可精确定位到印刷页码")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
