"""实训任务生成 Agent。

输入是能力图谱中的一个**能力单元**节点，输出是可直接上课用的实训任务。

之所以能做到「岗位任务 → 教学任务」的转化，是因为输入端已经带着
岗位侧的信息了：能力单元本身来自国家职业标准的「工作内容」，
它的技能点带着掌握程度要求。模型要做的是补上教学设计的部分 ——
情境、步骤、评分量规、常见错误 —— 而不是凭空想象这个岗位在干什么。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from app.core.enums import TaskDifficulty
from app.core.llm import Message
from app.schemas.common import SourceRef
from app.schemas.training import TrainingTaskDraft

_SYSTEM = """你是职业教育实训教学设计专家，擅长把企业真实工作任务转化为\
可在课堂上实施的实训任务。你设计的任务要让学生像在岗位上一样工作，\
而不是做一道练习题。"""

_DIFFICULTY_GUIDE = {
    TaskDifficulty.BEGINNER: "入门级：步骤明确，学生跟着做即可完成，重在建立规范意识",
    TaskDifficulty.INTERMEDIATE: "进阶级：包含需要判断与取舍的环节，如疑难样本如何处理",
    TaskDifficulty.ADVANCED: "挑战级：贴近真实项目复杂度，含质量控制与团队协作要求",
}

_PROMPT = """请为以下岗位能力设计一个实训任务。

## 目标能力

岗位：{job_name}
能力路径：{path}
能力单元：{unit_name}
{unit_description}

本单元包含的技能点：
{skill_lines}

## 可用依据

{context}

## 难度要求

{difficulty_guide}

## 设计要求

0. **任务必须紧扣上面给出的能力单元「{unit_name}」。**
   这是最重要的一条：任务的标题、情境、步骤都要围绕这项能力展开。
   不要套用其它领域的通用模板 —— 「业务数据采集」的任务就该是采集，
   不能写成标注；「标注质量管理」的任务就该是审核，不能写成标注。
1. **工作情境要具体**：交代清楚学生扮演什么角色、在什么公司、
   要交付什么。情境决定了学生是否理解这件事在岗位上为什么重要。
   避免「请完成以下练习」这类脱离岗位的说法。
2. **学习目标对应技能点**。每条目标的 `skill_code` **应当从上面列出的
   技能点中选择**。该单元没有的技能不要引入 —— 学生完成任务后，
   得分会按这些编码回写到能力画像，写错就是给学生记了错误的能力。
   确实对应不上的目标可以留空 `skill_code`，但不要乱填。
3. **步骤可执行**。每步说清做什么、做到什么程度算完成。
   `hint` 是给卡住的学生的提示，不是答案。
4. **评分量规要能真正区分水平**。各维度权重之和应为 100。
   每个维度至少给出「优秀 / 合格 / 待改进」的具体判据 ——
   写「标注准确率≥95%」而不是「标注质量好」。
5. **常见错误要来自真实作业经验**，说明错在哪、会造成什么后果、怎么改。
6. 若涉及数据安全、隐私或作业规范，写入 `safety_notes`。

## 输出格式

只输出 JSON，不要解释文字，不要 markdown 代码块标记。

**下面是字段结构说明，尖括号里是对内容的要求，不是可以照抄的文案 ——
请完全根据「{unit_name}」这项能力自行撰写：**

{{
  "title": "<紧扣该能力单元的任务名称>",
  "scenario": "<学生扮演的岗位角色 + 所在场景 + 要交付什么>",
  "difficulty": "{difficulty_value}",
  "est_minutes": <整数，建议课时分钟数>,
  "objectives": [
    {{"text": "<该任务要达成的具体能力>", "skill_code": "<从上方技能点中选，或留 null>"}}
  ],
  "steps": [
    {{"order": 1, "title": "<步骤名>", "detail": "<做什么、做到什么程度算完成>",
      "hint": "<给卡住的学生的提示，非答案>"}}
  ],
  "deliverables": ["<学生要提交的具体产出物>"],
  "rubric": [
    {{"dimension": "<评分维度>", "weight": <权重整数，全部维度合计 100>,
      "levels": [{{"level": "优秀", "criteria": "<可量化的判据>"}},
                 {{"level": "合格", "criteria": "<可量化的判据>"}},
                 {{"level": "待改进", "criteria": "<可量化的判据>"}}]}}
  ],
  "common_mistakes": [
    {{"mistake": "<真实作业中常犯的错>", "consequence": "<会造成什么后果>",
      "fix": "<怎么纠正>"}}
  ],
  "extensions": ["<学有余力者的拓展方向>"],
  "safety_notes": "<数据安全/隐私/作业规范要求，无则填 null>"
}}"""


@dataclass
class TaskGenerationInput:
    job_name: str
    unit_name: str
    unit_description: str | None = None
    #: 从根到该节点的路径，如 ["AI数据标注工程师", "数据标注能力", "原始数据清洗与标注"]
    path: list[str] = field(default_factory=list)
    #: [(skill_code, name, mastery_level)]
    skills: list[tuple[str, str, int | None]] = field(default_factory=list)
    difficulty: TaskDifficulty = TaskDifficulty.BEGINNER
    context: str | None = None


class TrainingTaskAgent(BaseAgent[TaskGenerationInput, TrainingTaskDraft]):
    name = "training_task"
    output_model = TrainingTaskDraft
    temperature = 0.4  # 教学设计需要一些创造性，但不能天马行空
    max_tokens = 3500
    retrieve_top_n = 6

    def retrieval_query(self, inp: TaskGenerationInput) -> str:
        skill_names = " ".join(name for _, name, _ in inp.skills[:4])
        base = f"{inp.unit_name} {skill_names} 实训 操作规范 教学要求"
        return f"{base} {inp.context}" if inp.context else base

    def render_prompt(
        self, inp: TaskGenerationInput, sources: list[SourceRef]
    ) -> list[Message]:
        if sources:
            context = "\n\n".join(
                f"[{s.marker}]（{s.label()}）\n{s.quote}" for s in sources
            )
        else:
            context = "（未检索到相关依据，请基于通用职业教育经验设计，并在评分量规上保持保守）"

        skill_lines = (
            "\n".join(
                f"  - {name}（{code}）"
                + (f" 掌握程度：{level}" if level else "")
                for code, name, level in inp.skills
            )
            or "  （该单元下暂无技能点）"
        )

        path = " → ".join(inp.path) if inp.path else inp.unit_name
        description = f"单元说明：{inp.unit_description}\n" if inp.unit_description else ""
        if inp.context:
            description += f"情境要求：{inp.context}\n"

        return [
            Message(role="system", content=_SYSTEM),
            Message(
                role="user",
                content=_PROMPT.format(
                    job_name=inp.job_name,
                    path=path,
                    unit_name=inp.unit_name,
                    unit_description=description,
                    skill_lines=skill_lines,
                    context=context,
                    difficulty_guide=_DIFFICULTY_GUIDE[inp.difficulty],
                    difficulty_value=inp.difficulty.value,
                ),
            ),
        ]

    def input_summary(self, inp: TaskGenerationInput) -> dict:
        return {
            "unit_name": inp.unit_name,
            "path": inp.path,
            "skills": [code for code, _, _ in inp.skills],
            "difficulty": inp.difficulty.value,
            "context": inp.context,
        }

    def reasoning_summary(
        self, parsed: TrainingTaskDraft, sources: list[SourceRef]
    ) -> str:
        weight_total = sum(d.weight for d in parsed.rubric)
        base = (
            f"依据「{parsed.title}」的能力要求设计了 {len(parsed.steps)} 个步骤、"
            f"{len(parsed.rubric)} 个评分维度（权重合计 {weight_total}）。"
        )
        return base + (
            f"参考了知识库中 {len(sources)} 条相关内容。"
            if sources
            else "未检索到知识库依据，建议教师核实后再发布。"
        )
