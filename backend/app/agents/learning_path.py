"""学习路径文案 Agent。

**注意这个 Agent 不排序。** 阶段的先后已由 services/path_ordering.py
按前置依赖拓扑排序 + 差距降序算好，模型拿到的是**既定顺序**，
只负责给每个阶段起名字、写说明、给学习建议。

之所以这样切分：顺序是「先学 A 再学 B」的结论，必须有依据、可复现、
可解释；而文案是表达问题，正是模型擅长的。把两者混在一个 prompt 里，
就再也说不清顺序到底是怎么来的了。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.core.llm import Message
from app.schemas.common import SourceRef


class PhaseCopy(BaseModel):
    """一个阶段的文案。顺序不在这里，由算法决定。"""

    order_index: int = Field(ge=0, le=20)
    title: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=10, max_length=400)
    est_hours: float = Field(default=8.0, ge=1.0, le=200.0)
    #: 给学生的具体建议，2~4 条
    suggestions: list[str] = Field(min_length=2, max_length=4)


class LearningPathCopy(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    #: 整体说明。可以解释「为什么这样排」，但不能改变顺序
    rationale: str = Field(min_length=10, max_length=600)
    phases: list[PhaseCopy] = Field(min_length=1, max_length=8)


_SYSTEM = """你是职业教育学习规划师。学习阶段的**先后顺序已经确定**，\
你的任务是为每个阶段写出清晰、可执行的说明，而不是重新排序。"""

_PROMPT = """为「{student_name}」制定通往「{job_name}」岗位的学习路径文案。

## 阶段划分（顺序已确定，不要改动）

{phase_lines}

## 顺序是怎么来的

{ordering_method}

这个顺序由算法根据**技能前置依赖**与**能力差距大小**计算得出，
不是主观安排。你可以在 rationale 里向学生解释这一点，
但**不要调整阶段顺序，也不要增删阶段**。

## 可参考的职业标准与教学资料

{context}

资料只用于让学习建议更贴合专业规范；不要从资料中臆造课程、平台链接或
不存在的实训资源。没有依据时应使用保守、通用的学习建议。

## 写作要求

1. 每个阶段的 `title` 要概括该阶段在学什么，不要写成「第一阶段」这种废话。
2. `description` 说明为什么这个阶段排在这里、学完能做什么。
   涉及差距时可以引用给出的数值。
3. `suggestions` 给 2~4 条具体可做的事，例如「用公开数据集练习 50 张图像的
   矩形框标注并自检」，不要写「认真学习相关知识」这类空话。
4. `est_hours` 按高职学生的实际投入估计。
5. **证据不足的技能要如实提醒**：若某项标注了「证据不足」，
   说明该项的差距判断可能不准，建议学生先补测再决定投入多少精力。

## 输出格式

只输出 JSON，不要解释文字，不要 markdown 代码块标记：

{{
  "title": "<路径名称>",
  "rationale": "<整体说明：为什么这样排、预计能达到什么水平>",
  "phases": [
    {{"order_index": 0, "title": "<阶段名>", "description": "<说明>",
      "est_hours": 12, "suggestions": ["<具体建议1>", "<具体建议2>"]}}
  ]
}}"""


@dataclass
class PathCopyInput:
    student_name: str
    job_name: str
    ordering_method: str
    #: [(order_index, [(skill_name, gap, reliable)], ordering_note)]
    phases: list[tuple[int, list[tuple[str, float, bool]], str]] = field(
        default_factory=list
    )


class LearningPathAgent(BaseAgent[PathCopyInput, LearningPathCopy]):
    name = "learning_path"
    output_model = LearningPathCopy
    temperature = 0.4
    max_tokens = 2500
    retrieve_top_n = 4

    def retrieval_query(self, inp: PathCopyInput) -> str:
        names = " ".join(
            name for _, skills, _ in inp.phases for name, _, _ in skills[:2]
        )
        return f"{inp.job_name} {names} 学习 培训 实训 课程"

    def render_prompt(self, inp: PathCopyInput, sources: list[SourceRef]) -> list[Message]:
        context = (
            "\n\n".join(
                f"[{source.marker}]（{source.label()}）\n{source.quote}"
                for source in sources
            )
            or "（未检索到相关依据，请使用保守、通用的职业教育学习建议）"
        )
        lines = []
        for index, skills, note in inp.phases:
            skill_text = "、".join(
                f"{name}（差距 {gap:.0f}{'，证据不足' if not reliable else ''}）"
                for name, gap, reliable in skills
            )
            lines.append(f"  阶段 {index}：{skill_text}\n    排序依据：{note}")

        return [
            Message(role="system", content=_SYSTEM),
            Message(
                role="user",
                content=_PROMPT.format(
                    student_name=inp.student_name,
                    job_name=inp.job_name,
                    phase_lines="\n".join(lines),
                    ordering_method=inp.ordering_method,
                    context=context,
                ),
            ),
        ]

    def input_summary(self, inp: PathCopyInput) -> dict:
        return {
            "job_name": inp.job_name,
            "phases": len(inp.phases),
            "skills": sum(len(s) for _, s, _ in inp.phases),
        }

    def reasoning_summary(
        self, parsed: LearningPathCopy, sources: list[SourceRef]
    ) -> str:
        return (
            f"依据算法给出的 {len(parsed.phases)} 个阶段撰写学习说明。"
            f"阶段顺序由前置依赖与能力差距确定，非模型排定。"
        )
