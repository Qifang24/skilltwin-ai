"""诊断测评出题 Agent。

只出**客观题**：诊断阶段要快速定位能力短板，客观题判分确定、
不引入额外的评分不确定性。主观题留给实训任务的 rubric 评分。

模型在这里只负责命题，**不负责判分、也不负责给学生打能力值** ——
那些是 services/scoring.py 里的确定性计算。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from app.core.llm import Message
from app.schemas.assessment import ItemBatch
from app.schemas.common import SourceRef

_SYSTEM = """你是职业教育测评命题专家，正在为岗位能力诊断编制客观题。\
你出的题要能真正区分「会」与「不会」，而不是考记忆力或文字游戏。"""

_PROMPT = """请为以下技能命制 {count} 道客观题，用于诊断学生的岗位能力水平。

## 目标技能

{skill_lines}

## 可用依据

{context}

## 命题要求

1. **考能力，不考记忆。** 优先设计「给定情境，判断该怎么做」的题，
   而不是「XX 的定义是什么」。例如：
   给出一段标注结果让学生判断哪里不符合规范，
   优于问「标注规范包括哪几条」。
2. **难度分布**：约 1/3 基础（difficulty 0.2~0.4）、
   1/2 中等（0.4~0.7）、其余偏难（0.7~0.9）。
   难度指的是**高职学生的作答难度**，不是知识本身的深浅。
3. **每题只标注一个主要考查技能**（`skill_code`），
   必须从上面列出的技能中选，不得自创。
4. **干扰项要合理**。错误选项应当是「看起来对但实际错」的常见误解，
   不要放明显荒谬的选项凑数 —— 那样题目区分不出真实水平。
5. **解析要说明为什么**，而不只是重复正确答案。
6. 题干与选项都用中文，避免使用「以下哪项不正确」这类双重否定。

## 题型与答案格式

- `single` 单选：options 给 A/B/C/D，answer_key 如 `["B"]`
- `multi` 多选：answer_key 如 `["A","C"]`，至少两个
- `judge` 判断：**options 留空数组**，answer_key 为 `["true"]` 或 `["false"]`

## 输出格式

只输出 JSON，不要解释文字，不要 markdown 代码块标记。
尖括号内是内容要求，不是可照抄的文案：

{{
  "items": [
    {{
      "stem": "<题干，含具体情境>",
      "item_type": "single",
      "options": [
        {{"key": "A", "text": "<选项>"}},
        {{"key": "B", "text": "<选项>"}},
        {{"key": "C", "text": "<选项>"}},
        {{"key": "D", "text": "<选项>"}}
      ],
      "answer_key": ["B"],
      "explanation": "<为什么选它，其它为什么不对>",
      "difficulty": 0.5,
      "skill_code": "<从上方技能中选>",
      "evidence_markers": ["S1"]
    }}
  ]
}}"""


@dataclass
class ItemGenerationInput:
    #: [(skill_code, name, description)]
    skills: list[tuple[str, str, str | None]] = field(default_factory=list)
    count: int = 4
    job_name: str = ""


class AssessmentItemAgent(BaseAgent[ItemGenerationInput, ItemBatch]):
    name = "assessment_item"
    output_model = ItemBatch
    temperature = 0.5  # 题目需要多样性，避免每次生成同一批
    max_tokens = 3500
    retrieve_top_n = 5

    def retrieval_query(self, inp: ItemGenerationInput) -> str:
        names = " ".join(name for _, name, _ in inp.skills)
        return f"{names} 操作规范 作业要求 技能要求 {inp.job_name}"

    def render_prompt(
        self, inp: ItemGenerationInput, sources: list[SourceRef]
    ) -> list[Message]:
        context = (
            "\n\n".join(f"[{s.marker}]（{s.label()}）\n{s.quote}" for s in sources)
            or "（未检索到相关依据，请基于通用职业认知命题，并留空 evidence_markers）"
        )
        skill_lines = "\n".join(
            f"  - {name}（{code}）" + (f"：{desc}" if desc else "")
            for code, name, desc in inp.skills
        )
        return [
            Message(role="system", content=_SYSTEM),
            Message(
                role="user",
                content=_PROMPT.format(
                    count=inp.count, skill_lines=skill_lines, context=context
                ),
            ),
        ]

    def input_summary(self, inp: ItemGenerationInput) -> dict:
        return {
            "skills": [code for code, _, _ in inp.skills],
            "count": inp.count,
            "job_name": inp.job_name,
        }

    def reasoning_summary(self, parsed: ItemBatch, sources: list[SourceRef]) -> str:
        base = f"命制 {len(parsed.items)} 道客观题"
        return base + (
            f"，参考知识库 {len(sources)} 条内容。" if sources else "，未检索到知识库依据。"
        )
