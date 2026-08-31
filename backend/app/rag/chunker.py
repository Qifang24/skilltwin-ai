"""分块。

原则：**每个 chunk 都必须知道自己出自哪一页、哪一节**。
检索命中后要能立刻回答「这句话在原文什么位置」，否则引用无法核验，
所谓 Evidence-Based 就成了空话。

策略：先按标题层级切成语义段，段内再按长度滑窗切分。
中文用字符数近似 token 数（bge 的中文分词基本是一字一 token）。
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

from app.core.config import settings
from app.rag.cleaner import clean_text, strip_page_furniture
from app.rag.loader import LoadedPage

#: "3.1 五级/初级工"、"1.7 普通受教育程度"、"4. 权重表"
#: 编号层级限制在 ≤2：三级编号（1.1.1）在职业标准里是**正文条目**而非标题，
#: 早期版本没限制层级，导致每条技能要求都被当成一节，切出 235 个平均 39 字的碎块。
#: 标题文字须以中文或字母开头。用 [^\d\s] 不够 —— 小数点也满足它，
#: "1.1.1 能利用设备…" 会被拆成编号 "1.1" + 标题 ".1 能利用…" 而误判为标题。
#: 编号限 1~2 位数字：章节号不会是 2022，这样可挡掉
#: "2022 年3月第1版…" 这类出版信息被误当成标题。
_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)[.、]?\s*([一-鿿A-Za-z（(《].{0,23})$")

#: 中文编号标题。政策与研究报告普遍用「（五）人才培养」「一、职业概况」，
#: 只认阿拉伯数字编号会漏掉它们，导致该段沿用上一个过期标题 ——
#: 引用会把读者指向错误的章节。
_CN_NUM = "一二三四五六七八九十百"
_HEADING_CN = re.compile(
    rf"^(?:[（(][{_CN_NUM}\d]{{1,3}}[）)]|[{_CN_NUM}]{{1,3}}[、．]|第[{_CN_NUM}\d]{{1,3}}[章节部分篇])"
    rf"\s*([一-鿿A-Za-z].{{0,23}})$"
)
#: 正文条目常以这些字开头，进一步排除误判
_CONTENT_PREFIX = re.compile(r"^(能|会|了解|熟悉|掌握|理解|具有|具备|应|须|不得)")


@dataclass
class Chunk:
    index: int
    text: str
    #: 印刷页码；该段跨页时取起始页
    page: str | None
    section: str | None
    #: 跨页时记录完整页范围，便于前端提示「见第 6–7 页」
    page_span: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)


def _is_heading(line: str) -> str | None:
    stripped = line.strip()
    if not (2 < len(stripped) <= 30):
        return None

    match = _HEADING.match(stripped) or _HEADING_CN.match(stripped)
    if not match:
        return None

    title = match.groups()[-1].strip()
    # 真标题不会以句中标点收尾，也不会以「能……」这类动作词开头
    if title.endswith(("。", "；", "，", "、", ":", "：")):
        return None
    if _CONTENT_PREFIX.match(title):
        return None
    return stripped


def _assemble(pages: list[LoadedPage]) -> tuple[str, list[int], list[str | None]]:
    """把多页拼成一篇，并记录每页在全文中的起始偏移，供反查页码。"""
    parts: list[str] = []
    offsets: list[int] = []
    page_labels: list[str | None] = []
    cursor = 0

    for page in pages:
        # 先去页眉页脚、再清洗：顺序反了会让页码行被合并进正文，无法剔除
        text = clean_text(strip_page_furniture(page.text, page.printed_page))
        if not text:
            continue
        offsets.append(cursor)
        page_labels.append(page.printed_page)
        parts.append(text)
        cursor += len(text) + 1  # +1 为拼接换行

    return "\n".join(parts), offsets, page_labels


def _page_at(offset: int, offsets: list[int], labels: list[str | None]) -> str | None:
    if not offsets:
        return None
    position = bisect_right(offsets, offset) - 1
    return labels[max(position, 0)]


def _pages_in_span(
    start: int, end: int, offsets: list[int], labels: list[str | None]
) -> list[str]:
    seen: list[str] = []
    for offset, label in zip(offsets, labels):
        if label and start < offset + 1 and offset < end:
            if label not in seen:
                seen.append(label)
    first = _page_at(start, offsets, labels)
    if first and first not in seen:
        seen.insert(0, first)
    return seen


def _section_at(offset: int, headings: list[tuple[int, str]]) -> str | None:
    """取该偏移之前最近的一个标题作为所属章节。"""
    if not headings:
        return None
    position = bisect_right([h[0] for h in headings], offset) - 1
    return headings[position][1] if position >= 0 else None


def _collect_headings(text: str) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    cursor = 0
    for line in text.splitlines():
        heading = _is_heading(line)
        if heading:
            headings.append((cursor, heading))
        cursor += len(line) + 1
    return headings


def chunk_pages(
    pages: list[LoadedPage],
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """把文档切成带页码与章节的 chunk。

    尺寸优先、按行边界收口：先定长滑窗，再回退到最近的换行处断开，
    避免把一条技能要求从中间劈开。章节名由「该块起始位置之前最近的标题」给出。
    """
    size = chunk_size or settings.chunk_size
    step_back = overlap if overlap is not None else settings.chunk_overlap
    stride = max(size - step_back, 1)

    full_text, offsets, labels = _assemble(pages)
    if not full_text.strip():
        return []

    headings = _collect_headings(full_text)
    chunks: list[Chunk] = []
    start = 0

    while start < len(full_text):
        end = min(start + size, len(full_text))
        if end < len(full_text):
            # 回退到窗口后半段里最后一个换行，保持条目完整
            newline = full_text.rfind("\n", start + stride // 2, end)
            if newline > start:
                end = newline

        piece = full_text[start:end].strip()
        if piece:
            span = _pages_in_span(start, end, offsets, labels)
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=piece,
                    page=span[0] if span else None,
                    section=_section_at(start, headings),
                    page_span=span,
                )
            )

        # 读到文末就收工。若继续走 start = end - overlap 的回退，
        # 由于 end 已固定在文末，start 会退化成每轮 +1，
        # 尾部会吐出几十个 1~64 字的碎片污染向量库。
        if end >= len(full_text) or end <= start:
            break
        start = max(end - step_back, start + 1)

    return chunks
