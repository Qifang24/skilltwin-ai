"""文档加载：把原始文件读成带页码的页面列表。

关键设计：区分 **PDF 物理页序** 与 **印刷页码**。
引用要给用户看的是印刷页码 —— 那才是他翻开纸质标准能对上的数字。
以《人工智能训练师国家职业技能标准》为例，PDF 第 10 页的页脚印的是 "6"，
若直接用物理页序做引用，用户按图索骥会翻错地方，等同于伪造出处。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}

#: 页脚里只含数字与空格的行，可能是印刷页码
_PAGE_NUMBER_LINE = re.compile(r"^[\d\s]{1,9}$")


@dataclass
class LoadedPage:
    """一页原文。"""

    #: 文件内的物理页序，从 1 开始
    page_index: int
    #: 页脚识别出的印刷页码；识别不到则为 None（此时引用只标章节，不编造页码）
    printed_page: str | None
    text: str


def _page_number_candidates(text: str) -> list[int]:
    """从页面首尾几行提取可能的印刷页码。

    抽取器对多位数页码常有两种毛病：数字被空格拆开，且顺序被打乱
    （实测本项目的国标 PDF 中 "10" 被抽成 "0 1"）。
    这里两种读法都作为候选给出，真伪交给 _resolve_printed_pages 用
    页码连续性去裁决 —— 不靠猜，靠约束。
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates: list[int] = []
    for line in (*lines[-3:], *lines[:2]):
        if not _PAGE_NUMBER_LINE.fullmatch(line):
            continue
        digits = line.split()
        if not digits or not all(d.isdigit() for d in digits):
            continue
        forward = "".join(digits)
        backward = "".join(reversed(digits))
        for value in (forward, backward):
            if 1 <= len(value) <= 4:
                candidates.append(int(value))
    return candidates


def _resolve_printed_pages(
    raw: list[tuple[int, list[int]]],
) -> dict[int, str]:
    """用「印刷页码随物理页序等差递增」这一约束，从候选中选出正确页码。

    做法：统计各页 (物理页序 - 候选页码) 的差值，取众数作为文档偏移量，
    再回头挑出与该偏移一致的候选。

    只接受**确实从页面上读到**的数字；读不到就留空，让引用退化为「只标章节」。
    绝不用偏移量凭空推算一个没读到的页码 —— 那是另一种形式的编造。
    """
    offsets: dict[int, int] = {}
    for page_index, candidates in raw:
        for candidate in candidates:
            offset = page_index - candidate
            if offset >= 0:
                offsets[offset] = offsets.get(offset, 0) + 1

    if not offsets:
        return {}

    best_offset, support = max(offsets.items(), key=lambda item: item[1])
    if support < 2:  # 支持度太低，说明这份文档没有稳定页码，宁可全部留空
        return {}

    resolved: dict[int, str] = {}
    for page_index, candidates in raw:
        for candidate in candidates:
            if page_index - candidate == best_offset:
                resolved[page_index] = str(candidate)
                break

    logger.info(
        "印刷页码解析完成",
        extra={"offset": best_offset, "support": support, "resolved": len(resolved)},
    )
    return resolved


def _load_pdf(path: Path) -> list[LoadedPage]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    texts = [(i, page.extract_text() or "") for i, page in enumerate(reader.pages, 1)]
    raw_candidates = [(i, _page_number_candidates(text)) for i, text in texts]
    resolved = _resolve_printed_pages(raw_candidates)

    return [
        LoadedPage(page_index=i, printed_page=resolved.get(i), text=text)
        for i, text in texts
    ]


def _load_docx(path: Path) -> list[LoadedPage]:
    """docx 无页概念，整篇作为一页；引用时只标章节。"""
    import docx

    document = docx.Document(str(path))
    text = "\n".join(p.text for p in document.paragraphs)
    return [LoadedPage(page_index=1, printed_page=None, text=text)]


def _load_text(path: Path) -> list[LoadedPage]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [LoadedPage(page_index=1, printed_page=None, text=text)]


def load_document(path: str | Path) -> list[LoadedPage]:
    """按扩展名加载文档。"""
    file_path = Path(path)
    if not file_path.exists():
        raise ValidationError(f"文件不存在：{file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValidationError(
            f"暂不支持的文件类型：{suffix}",
            detail={"supported": sorted(SUPPORTED_SUFFIXES)},
        )

    if suffix == ".pdf":
        pages = _load_pdf(file_path)
    elif suffix == ".docx":
        pages = _load_docx(file_path)
    else:
        pages = _load_text(file_path)

    logger.info(
        "文档加载完成",
        extra={
            "file": file_path.name,
            "pages": len(pages),
            "printed_pages_detected": sum(1 for p in pages if p.printed_page),
        },
    )
    return pages
