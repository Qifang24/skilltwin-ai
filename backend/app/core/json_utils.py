"""从 LLM 文本输出中稳健地提取 JSON。

现实情况：即便要求「只输出 JSON」，模型仍常常
  - 包在 ```json ... ``` 代码块里
  - 前面加一句「好的，以下是结果：」
  - 结尾多一个逗号

这一层只做**安全且确定性**的修复。修不好就抛错，交给 Agent 的
repair 重试环节让模型自己改 —— 不做激进的猜测式修补，
以免把模型的错误静默地「修」成另一个错误答案。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.errors import LLMOutputParseError

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def strip_code_fences(text: str) -> str:
    """取出 markdown 代码块内容；没有代码块则原样返回。"""
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()


def _find_balanced_span(text: str) -> tuple[int, int] | None:
    """定位第一个配对完整的 JSON 对象/数组。

    逐字符扫描并跳过字符串字面量，因此括号出现在字符串里也不会误判。
    """
    start = None
    opener = closer = ""
    for index, char in enumerate(text):
        if char in "{[":
            start = index
            opener = char
            closer = "}" if char == "{" else "]"
            break
    if start is None:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return start, index + 1
    return None


def _remove_trailing_commas(text: str) -> str:
    """删除 } 或 ] 前的多余逗号 —— 模型最常犯且完全安全可修的错误。"""
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def extract_json(text: str) -> Any:
    """从模型输出中解析出 JSON 值。

    依次尝试：直接解析 → 去代码块 → 截取配对片段 → 去尾逗号。
    全部失败则抛 LLMOutputParseError。
    """
    if not text or not text.strip():
        raise LLMOutputParseError("模型返回了空内容")

    candidates: list[str] = []

    stripped = text.strip()
    candidates.append(stripped)

    unfenced = strip_code_fences(text)
    if unfenced != stripped:
        candidates.append(unfenced)

    for base in list(candidates):
        span = _find_balanced_span(base)
        if span:
            candidates.append(base[span[0] : span[1]])

    # 最后才尝试去尾逗号，保证优先采用未经改动的原文
    candidates.extend(_remove_trailing_commas(c) for c in list(candidates))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    preview = stripped[:300] + ("…" if len(stripped) > 300 else "")
    raise LLMOutputParseError(
        "无法从模型输出中解析出 JSON", detail={"output_preview": preview}
    )


def extract_json_object(text: str) -> dict[str, Any]:
    """要求结果必须是 JSON 对象（而非数组或标量）。"""
    value = extract_json(text)
    if not isinstance(value, dict):
        raise LLMOutputParseError(
            f"期望 JSON 对象，实际得到 {type(value).__name__}",
            detail={"actual_type": type(value).__name__},
        )
    return value
