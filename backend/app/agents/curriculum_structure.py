"""Structured extraction of course records from an uploaded curriculum document."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.core.llm import Message
from app.schemas.common import SourceRef


class ExtractedCourse(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    course_code: str | None = None
    category: str | None = None
    total_hours: int | None = Field(default=None, ge=0)
    objectives: str | None = None
    description: str | None = None
    teaching_content: str | None = None
    knowledge_points: str | None = None
    practical_content: str | None = None
    learning_outcomes: str | None = None
    evidence_quotes: dict[str, str] = Field(default_factory=dict)


class CurriculumStructureResult(BaseModel):
    courses: list[ExtractedCourse]


@dataclass
class CurriculumStructureInput:
    filename: str
    document_text: str


_SYSTEM = """你是职业教育培养方案结构化助手。只能从上传原文提取课程，
不得凭常识补课程、课时、目标或教学内容。"""

_PROMPT = """请从【课程资料原文】提取课程结构。

要求：
1. 提取 name、course_code、category、total_hours、objectives、description、
   teaching_content、knowledge_points、practical_content、learning_outcomes。
2. 不存在的信息填 null，禁止编造或改写成原文没有的事实。
3. evidence_quotes 的 key 对应每个非空字段；value 必须是原文一字不差的连续片段。
4. 无法确认课程时返回 courses 空数组。
5. 只输出 JSON，不要 Markdown。

【课程资料原文】
{document_text}

输出：
{{"courses":[{{"name":"...","course_code":null,"category":null,"total_hours":null,
"objectives":null,"description":null,"teaching_content":null,"knowledge_points":null,
"practical_content":null,"learning_outcomes":null,"evidence_quotes":{{"name":"原文连续片段"}}}}]}}
"""


class CurriculumStructureAgent(BaseAgent[CurriculumStructureInput, CurriculumStructureResult]):
    name = "curriculum_structure"
    output_model = CurriculumStructureResult
    temperature = 0.0
    max_tokens = 5000

    def render_prompt(self, inp: CurriculumStructureInput, sources: list[SourceRef]) -> list[Message]:
        return [
            Message(role="system", content=_SYSTEM),
            Message(role="user", content=_PROMPT.format(document_text=inp.document_text[:30000])),
        ]

    def input_summary(self, inp: CurriculumStructureInput) -> dict:
        return {"filename": inp.filename, "document_chars": len(inp.document_text)}

    def reasoning_summary(self, parsed: CurriculumStructureResult, sources: list[SourceRef]) -> str:
        return f"从上传原文中结构化提取 {len(parsed.courses)} 门课程；每个非空字段均需通过连续原文引文校验。"
