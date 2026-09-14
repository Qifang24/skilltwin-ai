"""Evidence-bounded wording agent for curriculum optimization suggestions.

The agent may choose a supported action type and draft the human-facing text.
It never changes demand statistics, gap status, priority score, or ordering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.core.llm import Message
from app.schemas.common import SourceRef


ActionType = Literal[
    "add_course",
    "adjust_course_objectives",
    "add_teaching_content",
    "add_practicum",
    "add_project_practice",
    "adjust_hours",
    "strengthen_competency",
    "modify_course_content",
]


class OptimizationSuggestionDraft(BaseModel):
    skill_code: str
    action_type: ActionType
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=1200)
    reason: str = Field(min_length=1, max_length=800)


class OptimizationSuggestionBatch(BaseModel):
    suggestions: list[OptimizationSuggestionDraft]


@dataclass
class CurriculumOptimizationInput:
    job_id: str
    plan_id: str
    gaps: list[dict]


_SYSTEM = """你是职业教育培养方案优化助手。你只能根据输入的结构化事实起草建议，
不得修改需求频率、岗位数、覆盖状态、图谱掌握度、优先级或排序。"""

_PROMPT = """请为以下能力缺口逐条生成结构化培养方案优化建议。

硬性要求：
1. 每个输入 skill_code 恰好输出一次，不得增加或遗漏技能。
2. action_type 只能是：add_course、adjust_course_objectives、add_teaching_content、
   add_practicum、add_project_practice、adjust_hours、strengthen_competency、
   modify_course_content。
3. title 与 content 必须具体、可执行；不能编造学校、课程、课时或岗位数量。
4. reason 只复述输入中的岗位需求、图谱要求、课程覆盖状态和原文依据。
5. 只输出 JSON，不要 Markdown。

输入：
{payload}

输出格式：
{{"suggestions":[{{"skill_code":"...","action_type":"...","title":"...","content":"...","reason":"..."}}]}}
"""


class CurriculumOptimizationAgent(BaseAgent[CurriculumOptimizationInput, OptimizationSuggestionBatch]):
    name = "curriculum_optimization"
    output_model = OptimizationSuggestionBatch
    temperature = 0.1
    max_tokens = 3000

    def render_prompt(self, inp: CurriculumOptimizationInput, sources: list[SourceRef]) -> list[Message]:
        payload = {"job_id": inp.job_id, "plan_id": inp.plan_id, "gaps": inp.gaps}
        return [
            Message(role="system", content=_SYSTEM),
            Message(role="user", content=_PROMPT.format(payload=json.dumps(payload, ensure_ascii=False))),
        ]

    def input_summary(self, inp: CurriculumOptimizationInput) -> dict:
        return {"job_id": inp.job_id, "plan_id": inp.plan_id, "gap_count": len(inp.gaps), "skill_codes": [row["skill_code"] for row in inp.gaps]}

    def reasoning_summary(self, parsed: OptimizationSuggestionBatch, sources: list[SourceRef]) -> str:
        return "建议文字基于已计算的岗位需求、审核图谱与课程缺口起草；统计、优先级和证据链未由模型修改。"
