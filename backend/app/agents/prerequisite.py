"""技能前置依赖推断 Agent。

模型在这里只做一件事：**提出候选的前置关系**。
是否采纳由服务端的无环校验决定 —— 前置关系一旦成环，
拓扑排序无解，学习路径就排不出来。

这是「LLM 提议、代码裁决」模式的又一处应用：
让模型做它擅长的语义判断（学 A 之前是否需要先会 B），
让代码做它擅长的结构约束（不许成环）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.core.llm import Message
from app.schemas.common import SourceRef


class PrereqPair(BaseModel):
    #: 前置技能：要学 target 之前应先掌握它
    prerequisite: str = Field(min_length=1, max_length=96)
    target: str = Field(min_length=1, max_length=96)
    reason: str = Field(min_length=4, max_length=200)


class PrereqProposal(BaseModel):
    pairs: list[PrereqPair] = Field(default_factory=list, max_length=40)


_SYSTEM = """你是职业教育课程设计专家，正在梳理岗位技能之间的学习先后关系。"""

_PROMPT = """下面是「{job_name}」岗位的规范技能表。请判断它们之间的**学习先后依赖**。

## 技能表

{skill_lines}

## 判断标准

只在**确实存在学习依赖**时才建立关系，即：不先掌握 A，学 B 会明显吃力或无从下手。

应当建立的例子：
- 「数据清洗」→「数据标注」：不会清洗，拿到的原始数据没法标
- 「标注规范」→「标注质量审核」：不懂规范，无法判断标得对不对

**不应**建立的例子：
- 两项技能只是同属一个类别（都是标注类）—— 那是分类关系，不是依赖
- 泛泛的「基础更重要」—— 职业道德重要，但不构成学习其它技能的前置
- 互为前置 —— **绝不允许成环**，学习顺序必须能排出先后

## 要求

1. 宁缺勿滥。**关系过多会把学习路径拉成一条僵硬的长链**，
   失去「可并行学习」的灵活性。{max_pairs} 条以内，通常 5~12 条就够。
2. 编码必须来自上面的技能表，不得自创。
3. 每条都要写清依赖理由。

## 输出格式

只输出 JSON，不要解释文字，不要 markdown 代码块标记：

{{
  "pairs": [
    {{"prerequisite": "<先学的技能编码>", "target": "<后学的技能编码>",
      "reason": "<为什么必须先学前者>"}}
  ]
}}

若判断这些技能之间没有明确的学习依赖，返回 {{"pairs": []}}。"""


@dataclass
class PrereqInput:
    job_name: str
    #: [(skill_code, name, category)]
    skills: list[tuple[str, str, str]] = field(default_factory=list)
    max_pairs: int = 14


class PrerequisiteAgent(BaseAgent[PrereqInput, PrereqProposal]):
    name = "prerequisite"
    output_model = PrereqProposal
    temperature = 0.1  # 结构判断，压低随机性
    max_tokens = 2500
    retrieve_top_n = 4

    def retrieval_query(self, inp: PrereqInput) -> str:
        return f"{inp.job_name} 技能要求 工作内容 先后 基础 进阶 职业技能等级"

    def render_prompt(
        self, inp: PrereqInput, sources: list[SourceRef]
    ) -> list[Message]:
        skill_lines = "\n".join(
            f"  {code:30s} {name}（{category}）" for code, name, category in inp.skills
        )
        return [
            Message(role="system", content=_SYSTEM),
            Message(
                role="user",
                content=_PROMPT.format(
                    job_name=inp.job_name,
                    skill_lines=skill_lines,
                    max_pairs=inp.max_pairs,
                ),
            ),
        ]

    def input_summary(self, inp: PrereqInput) -> dict:
        return {"job_name": inp.job_name, "skills": len(inp.skills)}

    def reasoning_summary(
        self, parsed: PrereqProposal, sources: list[SourceRef]
    ) -> str:
        return f"提出 {len(parsed.pairs)} 条学习依赖，待无环校验后采纳。"
