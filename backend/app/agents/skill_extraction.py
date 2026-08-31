"""从职业标准原文中抽取规范技能点。

设计要点：模型**只做命名与归类**，不负责判断「该不该有这个技能」——
技能是否成立由标准原文决定。因此每条候选必须附上原文精确引文，
校验不过的一律丢弃（见 scripts/extract_skills.py 的核验环节）。

这样即便模型幻觉出一个「Label Studio 高级插件开发」技能，
只要它编不出对应的原文引文，就进不了技能表。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.base import BaseAgent
from app.core.llm import Message
from app.schemas.common import SourceRef
from app.schemas.skill import SkillExtractionResult

_SYSTEM = """你是职业教育领域的岗位能力分析专家，正在把国家职业技能标准的条文\
整理成结构化的规范技能表。你的产出会成为一个教学系统的数据主键，因此命名必须\
克制、稳定、可复用。"""

_PROMPT = """下面是《人工智能训练师国家职业技能标准（2021年版）》的一段原文。

【原文】
{chunk_text}

请从中抽取**规范技能点**。

## 命名规则

skill_code 格式为 `<前缀>.<名称>`，全小写 ASCII，词间用下划线：

| 前缀 | category | 适用范围 | 示例 |
|---|---|---|---|
| prog | programming | 编程语言与工程能力 | prog.python |
| data | data | 数据采集/清洗/转换/统计/归类 | data.cleaning |
| annot | annotation | **数据标注作业本身**（按数据形态或标注形式细分） | annot.image、annot.text |
| tool | tool | 具体工具软件 | tool.label_studio |
| ai | ai_theory | AI **理论概念**（模型、算法、评估指标） | ai.model_eval |
| quality | quality | 质量审核、作业规范、法规合规 | quality.audit、quality.compliance |
| soft | soft | **非技术**通用职业能力 | soft.teamwork |

**前缀必须与 category 严格对应。**易错点：

- `soft` **只放**职业道德、沟通表达、团队协作、学习能力、时间管理这类
  非技术能力。法律法规、网络安全属于**知识与合规**，归 `quality`，不归 soft。
- `ai` 只放理论概念。系统部署、运维、数据库管理是**操作类**，归 `data` 或 `tool`。

## 硬性要求

1. `evidence_quote` 必须是上面【原文】里**一字不差的连续片段**，用于核验。
   不要改写、不要拼接、不要加省略号。抄不出原文就不要输出这条技能。
2. 技能点要**可复用、可测评**。抽「数据清洗」而不是「能根据标注规范和要求完成
   文本、视觉、语音数据清洗」——后者是任务描述，不是技能。
3. 粒度适中：一段原文通常产出 2~6 个技能点。宁少勿滥。
4. 只抽原文**确实支持**的技能。原文没提到 Label Studio 就不要凭常识补上。
5. `aliases` 写该技能在业界的其他常见叫法（含英文、缩写、大小写变体）。
6. **技能名必须具体到能出一道测评题**。禁止 general / basic / common / misc /
   labeling 这类无信息量的名称，也不要「智能系统」「业务数据」这种宽泛到
   无法评价的词。写 `annot.image` 不写 `annot.general`。
7. 同一概念只出一个技能点。不要把「培训计划」「培训方案」「培训材料」
   拆成三条 —— 合并成一条。
8. **只抽从业者本人要掌握的能力。** 标准里关于「鉴定考核如何组织」的条文
   —— 监考人员与考生配比、鉴定时间、鉴定场所设备、申报条件、考评方式 ——
   描述的是认证考试的实施办法，不是从业者的岗位技能，一律不抽。
9. 出版信息、目录、致谢、标准制定说明同样不含技能，返回空列表即可。

## 输出格式

只输出 JSON，不要解释文字，不要 markdown 代码块标记：

{{
  "skills": [
    {{
      "skill_code": "data.cleaning",
      "name_zh": "数据清洗",
      "name_en": "Data Cleaning",
      "category": "data",
      "description": "按标注规范对文本、图像、语音原始数据进行清洗预处理。",
      "aliases": ["数据预处理", "Data Cleaning", "清洗"],
      "evidence_quote": "能根据标注规范和要求, 完成文本、视觉、语音数据清洗"
    }}
  ]
}}

若这段原文不含可抽取的技能点（例如只是目录、鉴定时间说明），返回 {{"skills": []}}。"""


@dataclass
class SkillExtractionInput:
    chunk_id: str
    chunk_text: str
    page: str | None = None
    section: str | None = None


class SkillExtractionAgent(BaseAgent[SkillExtractionInput, SkillExtractionResult]):
    name = "skill_extraction"
    output_model = SkillExtractionResult
    #: 命名要稳定可复现，温度压到 0
    temperature = 0.0
    max_tokens = 2000

    def render_prompt(
        self, inp: SkillExtractionInput, sources: list[SourceRef]
    ) -> list[Message]:
        return [
            Message(role="system", content=_SYSTEM),
            Message(role="user", content=_PROMPT.format(chunk_text=inp.chunk_text)),
        ]

    def input_summary(self, inp: SkillExtractionInput) -> dict:
        return {
            "chunk_id": inp.chunk_id,
            "page": inp.page,
            "section": inp.section,
            "chunk_chars": len(inp.chunk_text),
        }
