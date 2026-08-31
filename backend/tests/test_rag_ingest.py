"""文档加载、清洗、分块测试。

其中两条是真实踩过的坑的回归测试：
  - 两位数印刷页码被 pypdf 逆序抽出（"10" → "0 1"），会静默产生错误引用
  - 分块尾部退化，吐出几十个 1~64 字碎片污染向量库
"""

from __future__ import annotations

from app.rag.chunker import _is_heading, chunk_pages
from app.rag.cleaner import clean_text, strip_page_furniture
from app.rag.loader import LoadedPage, _page_number_candidates, _resolve_printed_pages


# ------------------------------------------------------------------ 清洗
def test_removes_spacing_inside_chinese() -> None:
    assert clean_text("国 家 职 业 技 能 标 准") == "国家职业技能标准"


def test_removes_space_around_chinese_punctuation() -> None:
    assert clean_text("能利用设备 、 工具") == "能利用设备、工具"


def test_normalises_split_numbering() -> None:
    assert clean_text("1. 1. 1能利用设备").startswith("1.1.1 能利用设备")


def test_joins_wrapped_sentence() -> None:
    text = "1.1.1 能利用设备、工具\n等完成原始业务数据采集"
    assert "工具等完成原始业务数据采集" in clean_text(text)


def test_heading_is_not_glued_to_following_text() -> None:
    """标题被粘进正文会让章节名变成一长串，引用时无法定位。"""
    cleaned = clean_text("3.1 五级/初级工\n职业功能工作内容")
    assert cleaned.splitlines()[0] == "3.1 五级/初级工"


def test_drops_watermark_lines() -> None:
    cleaned = clean_text("正文内容\n学兔兔 www.bzfxw.com 标准下载\n更多正文")
    assert "学兔兔" not in cleaned
    assert "bzfxw" not in cleaned


def test_collapses_slash_spacing() -> None:
    assert "五级/初级工" in clean_text("五级/ 初级工")


def test_strip_page_furniture_removes_page_number_and_code() -> None:
    text = "正文\n6\n职业编码: 4-04-05-05"
    assert strip_page_furniture(text, "6") == "正文"


# -------------------------------------------------------------- 印刷页码
def test_single_digit_page_candidate() -> None:
    assert 6 in _page_number_candidates("正文内容\n6\n职业编码: 4-04-05-05")


def test_reversed_two_digit_page_is_a_candidate() -> None:
    """实测 pypdf 把 "10" 抽成 "0 1"，两种读法都要作为候选。"""
    candidates = _page_number_candidates("正文\n0 1\n职业编码: 4-04-05-05")
    assert 10 in candidates


def test_page_offset_resolves_reversed_digits() -> None:
    """靠页码连续性裁决，而不是猜数字顺序。

    物理页 10→印刷 6，偏移固定为 4；因此 "0 1" 应被判为 10 而非 1。
    """
    raw = [
        (10, [6]),
        (11, [7]),
        (12, [8]),
        (13, [9]),
        (14, [1, 10]),  # "0 1" 的两种读法
        (15, [11, 11]),
    ]
    resolved = _resolve_printed_pages(raw)
    assert resolved[14] == "10"
    assert resolved[10] == "6"


def test_unstable_pagination_yields_no_page_numbers() -> None:
    """页码不连续时宁可全部留空，也不要给出错误页码。"""
    assert _resolve_printed_pages([(1, [77]), (2, [3])]) == {}


def test_page_never_invented_when_unreadable() -> None:
    """读不到页码就留空 —— 不用偏移量凭空推算，那是另一种编造。"""
    raw = [(1, [1]), (2, [2]), (3, [3]), (4, [])]
    resolved = _resolve_printed_pages(raw)
    assert 4 not in resolved


# ---------------------------------------------------------------- 标题
def test_content_line_is_not_treated_as_heading() -> None:
    """三级编号是正文条目。早期误判导致切出 235 个平均 39 字的碎块。"""
    assert _is_heading("1.1.1 能利用设备、工具等完成原始业务数据采集") is None
    assert _is_heading("2.1.1 数据清洗工具使用知识") is None


def test_real_heading_is_detected() -> None:
    assert _is_heading("3.1 五级/初级工") == "3.1 五级/初级工"
    assert _is_heading("2. 基本要求") == "2. 基本要求"


# ---------------------------------------------------------------- 分块
def _pages(text: str, n: int = 1) -> list[LoadedPage]:
    return [LoadedPage(page_index=i + 1, printed_page=str(i + 1), text=text) for i in range(n)]


def test_chunks_respect_size_and_have_no_degenerate_tail() -> None:
    """回归：尾部曾退化成几十个 1~64 字碎片。"""
    body = "\n".join(f"{i}.第{i}条要求，能够完成对应的数据标注作业任务。" for i in range(200))
    chunks = chunk_pages(_pages(body), chunk_size=512, overlap=64)

    assert chunks
    lengths = [c.char_count for c in chunks]
    # 除最后一块外都应接近目标长度；任何一块都不该是碎片
    assert min(lengths) > 64, f"出现碎片块：{sorted(lengths)[:5]}"
    assert max(lengths) <= 512


def test_chunk_carries_page_and_section() -> None:
    text = "3.1 五级/初级工\n" + "能根据标注规范完成数据标注作业。" * 40
    chunks = chunk_pages(_pages(text), chunk_size=256, overlap=32)

    assert chunks[0].page == "1"
    assert chunks[0].section == "3.1 五级/初级工"


def test_empty_document_yields_no_chunks() -> None:
    assert chunk_pages(_pages("   ")) == []
