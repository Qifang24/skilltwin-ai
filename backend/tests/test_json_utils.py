"""JSON 提取的容错能力测试。

这些都是中文大模型实际会犯的错误形态，不是假想的边界情况。
"""

from __future__ import annotations

import pytest

from app.core.errors import LLMOutputParseError
from app.core.json_utils import extract_json, extract_json_object


def test_plain_json() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_markdown_fenced_json() -> None:
    text = '```json\n{"skill": "Label Studio", "level": 3}\n```'
    assert extract_json(text) == {"skill": "Label Studio", "level": 3}


def test_fence_without_language_tag() -> None:
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_leading_and_trailing_prose() -> None:
    """模型最常见的毛病：前面来一句「好的，以下是结果」。"""
    text = '好的，以下是分析结果：\n\n{"skills": ["python"]}\n\n希望对你有帮助！'
    assert extract_json(text) == {"skills": ["python"]}


def test_braces_inside_string_do_not_break_scanner() -> None:
    text = '{"note": "这里有个大括号 } 和中括号 ]", "ok": true}'
    assert extract_json(text) == {"note": "这里有个大括号 } 和中括号 ]", "ok": True}


def test_escaped_quotes_inside_string() -> None:
    text = r'{"quote": "他说\"紧贴边缘\"是硬性要求"}'
    assert extract_json(text)["quote"] == '他说"紧贴边缘"是硬性要求'


def test_trailing_comma_is_repaired() -> None:
    assert extract_json('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}
    assert extract_json('{"items": [1, 2, 3,],}') == {"items": [1, 2, 3]}


def test_nested_structure() -> None:
    text = """```json
{
  "job": "AI数据标注工程师",
  "competencies": [
    {"name": "数据标注能力", "skills": [{"code": "annot.bbox", "level": 3}]}
  ]
}
```"""
    result = extract_json_object(text)
    assert result["competencies"][0]["skills"][0]["code"] == "annot.bbox"


def test_array_at_top_level() -> None:
    assert extract_json('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_extract_json_object_rejects_array() -> None:
    with pytest.raises(LLMOutputParseError, match="期望 JSON 对象"):
        extract_json_object('[{"a": 1}]')


def test_empty_output_raises() -> None:
    with pytest.raises(LLMOutputParseError, match="空内容"):
        extract_json("   ")


def test_unparseable_output_raises_with_preview() -> None:
    with pytest.raises(LLMOutputParseError) as exc_info:
        extract_json("我不知道该怎么回答这个问题。")
    assert "output_preview" in exc_info.value.detail
