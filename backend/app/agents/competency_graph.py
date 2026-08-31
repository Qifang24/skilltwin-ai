"""岗位能力图谱生成 Agent。

两条约束让它不至于凭空编：

  1. **技能点只能从已有技能表里选。** prompt 里给出全部可用 skill_code，
     模型不得自创。服务端还会再校验一遍，非法编码的节点会被降级或丢弃。
  2. **每个能力节点都要标注依据编号 [Sn]。** 检索片段来自真实入库的
     国标与教学标准，模型引用了不存在的编号一眼可辨。

模型在这里做的是「把标准条文组织成树」，不是「决定这个岗位需要什么能力」——
后者由标准决定。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from app.core.llm import Message
from app.schemas.common import SourceRef
from app.schemas.competency import CompetencyGraphDraft
from app.services.citation_verification_service import CitationClaim

_SYSTEM = """你是职业教育岗位能力分析专家，正在把国家职业技能标准与专业教学标准\
的条文，整理成可用于教学设计的岗位能力图谱。你的产出会成为一个教学系统的数据中枢，\
因此层级必须清晰、粒度必须一致、每一条都要有出处。"""

_PROMPT = """请为岗位「{job_name}」构建能力图谱。

## 可用依据

以下是从国家职业技能标准、专业教学标准与行业报告中检索到的原文片段：

{context}

## 可用技能编码

技能点与知识点**必须**从下表中选择 `skill_code`，**不得自创**：

{skill_table}

## 层级要求

严格三层，对应职业标准的表格结构：

```
competency        能力（对应「职业功能」，如 数据标注）        4~6 个
└─ competency_unit  能力单元（对应「工作内容」，如 原始数据清洗与标注） 每个 2~4 个
   └─ skill_point     技能点（对应「技能要求」）              每个 2~5 个
      knowledge_point  知识点（对应「相关知识要求」）
```

- `skill_point` 与 `knowledge_point` 是同一层的兄弟节点，都挂在 competency_unit 下
- 这两类节点**必须**填 `skill_code` 和 `mastery_level`
- `competency` 与 `competency_unit` **不填** `skill_code`

## mastery_level（掌握程度）

按高职毕业生入职岗位的要求填：1 了解 / 2 理解 / 3 掌握 / 4 熟练。
核心作业技能通常 3，辅助性了解内容 1~2。这个值会成为学生能力测评的目标基线，
请按标准的实际要求填，不要一律给高分。

## 依据标注

每个 `competency` 和 `competency_unit` 节点都要在 `evidence_markers` 里
写出支撑它的片段编号（如 ["S1","S3"]）。**只能引用上面真实出现过的编号**。
找不到依据的能力，宁可不写。

{focus_hint}

## 输出格式

只输出 JSON，不要解释文字，不要 markdown 代码块标记：

{{
  "summary": "一句话概括该岗位的能力构成",
  "competencies": [
    {{
      "node_type": "competency",
      "name": "数据标注能力",
      "description": "……",
      "evidence_markers": ["S1"],
      "children": [
        {{
          "node_type": "competency_unit",
          "name": "原始数据清洗与标注",
          "description": "……",
          "evidence_markers": ["S1"],
          "children": [
            {{
              "node_type": "skill_point",
              "name": "视觉数据标注",
              "description": "……",
              "skill_code": "annot.image",
              "mastery_level": 3,
              "children": []
            }}
          ]
        }}
      ]
    }}
  ]
}}"""


@dataclass
class GraphGenerationInput:
    job_id: str
    job_name: str
    #: 可选的 skill_code，来自技能表
    available_skills: list[tuple[str, str, str]] = field(default_factory=list)
    focus: str | None = None


class CompetencyGraphAgent(BaseAgent[GraphGenerationInput, CompetencyGraphDraft]):
    name = "competency_graph"
    output_model = CompetencyGraphDraft
    temperature = 0.1  # 结构性任务，压低随机性
    max_tokens = 4000
    retrieve_top_n = 8

    def retrieval_query(self, inp: GraphGenerationInput) -> str:
        """检索该岗位的职业功能、工作内容与技能要求条文。"""
        base = f"{inp.job_name} 职业功能 工作内容 技能要求 相关知识要求 数据标注"
        return f"{base} {inp.focus}" if inp.focus else base

    def render_prompt(
        self, inp: GraphGenerationInput, sources: list[SourceRef]
    ) -> list[Message]:
        if sources:
            context = "\n\n".join(
                f"[{s.marker}]（{s.label()}）\n{s.quote}" for s in sources
            )
        else:
            context = "（未检索到相关依据，请仅依据通用职业认知谨慎生成，并留空 evidence_markers）"

        skill_table = "\n".join(
            f"  {code:28s} {name}（{category}）"
            for code, name, category in inp.available_skills
        ) or "  （技能表为空）"

        focus_hint = f"\n## 侧重方向\n\n{inp.focus}\n" if inp.focus else ""

        return [
            Message(role="system", content=_SYSTEM),
            Message(
                role="user",
                content=_PROMPT.format(
                    job_name=inp.job_name,
                    context=context,
                    skill_table=skill_table,
                    focus_hint=focus_hint,
                ),
            ),
        ]

    def input_summary(self, inp: GraphGenerationInput) -> dict:
        return {
            "job_id": inp.job_id,
            "job_name": inp.job_name,
            "available_skills": len(inp.available_skills),
            "focus": inp.focus,
        }

    def citation_claims(self, parsed: CompetencyGraphDraft) -> list[CitationClaim]:
        """按能力/能力单元落盘，避免整张图谱共用一条笼统引用。"""
        claims: list[CitationClaim] = []

        def walk(node) -> None:  # noqa: ANN001
            if node.evidence_markers:
                claims.append(
                    CitationClaim(
                        text=f"图谱节点：{node.name}",
                        markers=tuple(node.evidence_markers),
                    )
                )
            for child in node.children:
                walk(child)

        for competency in parsed.competencies:
            walk(competency)
        return claims or super().citation_claims(parsed)

    def reasoning_summary(
        self, parsed: CompetencyGraphDraft, sources: list[SourceRef]
    ) -> str:
        units = sum(len(c.children) for c in parsed.competencies)
        if sources:
            return (
                f"依据知识库中 {len(sources)} 条标准条文，"
                f"归纳出 {len(parsed.competencies)} 项能力、{units} 个能力单元。"
            )
        return (
            f"未检索到知识库依据，仅凭通用职业认知生成 "
            f"{len(parsed.competencies)} 项能力，需人工核实后使用。"
        )
