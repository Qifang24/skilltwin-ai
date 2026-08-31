"""文本清洗。

中文 PDF 抽取出来的文字有一批固定毛病，不清理会直接毁掉检索质量：

    国 家 职 业 技 能 标 准        字间被塞进空格
    能利用设备 、 工具            标点前后多空格
    3. 1　五级/初级工             编号被拆散、全角空格
    ……等完成原始\n业务数据采集     句子被换行截断
    学兔兔 www.bzfxw.com          转载站水印

清洗只做**确定性、可逆推**的规整，不改写语义、不删正文。
"""

from __future__ import annotations

import re

CJK = r"一-鿿㐀-䶿"
CJK_PUNCT = r"。，、；：？！（）《》〈〉「」『』【】…—～·”“‘’"

#: 已知的转载水印/广告行，整行丢弃
_NOISE_LINE_PATTERNS = [
    re.compile(r"学兔兔"),
    re.compile(r"www\.bzfxw\.com"),
    re.compile(r"标准下载\s*$"),
]

_CJK_SPACE = re.compile(rf"(?<=[{CJK}])[ \t]+(?=[{CJK}])")
_SPACE_BEFORE_CJK_PUNCT = re.compile(rf"[ \t]+(?=[{CJK_PUNCT}])")
_SPACE_AFTER_CJK_PUNCT = re.compile(rf"(?<=[{CJK_PUNCT}])[ \t]+")
_CJK_DIGIT_SPACE = re.compile(rf"(?<=[{CJK}])[ \t]+(?=\d)|(?<=\d)[ \t]+(?=[{CJK}])")
#: "五级/ 初级工" → "五级/初级工"
_CJK_SLASH_SPACE = re.compile(rf"(?<=[{CJK}])\s*/\s*(?=[{CJK}])")
#: 章节标题行（编号层级 ≤2 且标题短），合并断行时不得把它粘进正文。
#: 标题文字必须以非数字开头 —— 否则 "1.1.1 能利用设备…" 会被误判为
#: 编号 "1.1" + 标题 "1 能利用…"，进而阻止正文断行合并。
_HEADING_LINE = re.compile(rf"^\d{{1,2}}(?:\.\d{{1,2}})?[.、]?\s*[{CJK}A-Za-z（(《]\S{{1,23}}$")
#: 编号与中文之间补回一个空格，保证 "3.1五级" 与 "3. 1 五级" 归一到同一形态
_NUMBERING_SPACING = re.compile(rf"^(\d+(?:\.\d+)*)[.、]?\s*(?=[{CJK}])", re.MULTILINE)
#: "1. 1. 1能……" → "1.1.1 能……"
_SPLIT_NUMBERING = re.compile(r"(?<!\d)(\d+)\.\s+(\d+)(?:\.\s+(\d+))?")
_MULTI_BLANK = re.compile(r"\n{3,}")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def _drop_noise_lines(text: str) -> str:
    kept = [
        line
        for line in text.splitlines()
        if not any(pattern.search(line) for pattern in _NOISE_LINE_PATTERNS)
    ]
    return "\n".join(kept)


def _fix_numbering(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        parts = [g for g in match.groups() if g]
        return ".".join(parts) + " "

    return _SPLIT_NUMBERING.sub(repl, text)


def _join_wrapped_lines(text: str) -> str:
    """合并被 PDF 排版截断的中文句子。

    只在「上一行以中文结尾且不是句末标点」且「下一行以中文开头」时合并，
    避免把表格行、编号行错误地粘在一起。
    """
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if out and out[-1]:
            prev = out[-1]
            ends_mid_sentence = (
                re.search(rf"[{CJK}]$", prev) is not None
                and not re.search(r"[。！？；：]$", prev)
            )
            starts_with_cjk = re.match(rf"^[{CJK}]", stripped) is not None
            # 标题自成一行：粘进正文会让章节名变成一长串，引用时无法定位
            prev_is_heading = _HEADING_LINE.match(prev) is not None
            if ends_mid_sentence and starts_with_cjk and not prev_is_heading:
                out[-1] = prev + stripped
                continue
        out.append(stripped)
    return "\n".join(out)


def clean_text(text: str, *, join_wrapped: bool = True) -> str:
    """清洗单页/单段文本。"""
    if not text:
        return ""

    text = text.replace("　", " ")  # 全角空格
    text = text.replace("\xa0", " ")  # 不换行空格
    text = _drop_noise_lines(text)

    text = _CJK_SPACE.sub("", text)
    text = _CJK_DIGIT_SPACE.sub("", text)
    text = _CJK_SLASH_SPACE.sub("/", text)
    text = _SPACE_BEFORE_CJK_PUNCT.sub("", text)
    text = _SPACE_AFTER_CJK_PUNCT.sub("", text)
    text = _fix_numbering(text)
    text = _NUMBERING_SPACING.sub(r"\1 ", text)

    if join_wrapped:
        text = _join_wrapped_lines(text)

    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip()


def strip_page_furniture(text: str, printed_page: str | None) -> str:
    """去掉页眉页脚残留。

    **必须在 clean_text 之前调用**：clean_text 会合并断行，把孤立的页码行
    与下方的页脚粘成 "1 职业编码: 4-04-05-05"，届时两条规则都匹配不上，
    这行垃圾就会被当成章节标题跟着引用一起显示出去。
    """
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue
        if printed_page and stripped == printed_page:
            continue
        # 纯数字（含被抽取器拆开的 "0 1"）视为页码行
        if re.fullmatch(r"[\d\s]{1,9}", stripped):
            continue
        if re.fullmatch(r"职业编码[:：]?\s*[\d\-]+", stripped):
            continue
        lines.append(line)
    return "\n".join(lines).strip()
