"""全域领域词汇表。

模型层与 Schema 层共用，保证「数据库里存的」与「API 里传的」是同一套枚举，
避免出现同义不同写的取值漂移。
"""

from __future__ import annotations

import sys
from enum import Enum, IntEnum

from sqlalchemy import Enum as SAEnum

if sys.version_info >= (3, 11):  # pragma: no cover - 取决于运行时版本
    from enum import StrEnum
else:  # Python 3.10：enum.StrEnum 尚不存在，用等价实现兜底

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """3.11 之前的 StrEnum 替代品：成员即其字符串值。"""

        def __str__(self) -> str:
            return str(self.value)


def db_enum(enum_cls: type, name: str) -> SAEnum:
    """构造非 native 的 VARCHAR + CHECK 约束列类型。

    native_enum=False 让 SQLite / Postgres 行为一致；
    values_callable 保证入库的是枚举的 value 而非 name。
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda e: [item.value for item in e],
    )


class NodeType(StrEnum):
    """能力图谱节点层级：产业 → 岗位群 → 岗位 → 工作任务 → 能力 → 能力单元 → 技能点/知识点。"""

    INDUSTRY = "industry"
    JOB_FAMILY = "job_family"
    JOB = "job"
    WORK_TASK = "work_task"
    COMPETENCY = "competency"
    COMPETENCY_UNIT = "competency_unit"
    SKILL_POINT = "skill_point"
    KNOWLEDGE_POINT = "knowledge_point"


#: 这两类节点必须挂载 skill_code —— 它们是学生能力向量的维度来源。
SKILL_BEARING_NODE_TYPES: frozenset[NodeType] = frozenset(
    {NodeType.SKILL_POINT, NodeType.KNOWLEDGE_POINT}
)


class GraphStatus(StrEnum):
    """图谱生命周期。只有 approved 的图谱可被下游引用。"""

    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class EdgeRelation(StrEnum):
    """跨层关系（树形父子关系由 parent_id 表达，不进这张表）。"""

    PREREQ = "prereq"  # 前置依赖，学习路径拓扑排序的依据
    RELATED = "related"
    ASSESSED_BY = "assessed_by"


class MasteryLevel(IntEnum):
    """掌握程度要求，对齐职业教育常用四级表述。"""

    AWARE = 1  # 了解
    UNDERSTAND = 2  # 理解
    APPLY = 3  # 掌握
    PROFICIENT = 4  # 熟练

    @property
    def label_zh(self) -> str:
        return {1: "了解", 2: "理解", 3: "掌握", 4: "熟练"}[self.value]


class SkillStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class SkillCategory(StrEnum):
    """技能大类，用于雷达图分组与图表着色。"""

    PROGRAMMING = "programming"  # 编程语言与工程能力
    DATA = "data"  # 数据处理
    ANNOTATION = "annotation"  # 数据标注
    TOOL = "tool"  # 工具链
    AI_THEORY = "ai_theory"  # AI 基础理论
    QUALITY = "quality"  # 质量与规范
    SOFT = "soft"  # 职业素养


class SourceType(StrEnum):
    """知识来源类型。排序大致代表权威性，用于检索结果的置信度加权。"""

    NATIONAL_STANDARD = "national_standard"  # 国家职业技能标准
    TEACHING_STANDARD = "teaching_standard"  # 职业教育专业教学标准
    INDUSTRY_SPEC = "industry_spec"  # 行业规范
    TEXTBOOK = "textbook"  # 权威教材
    LAB_MANUAL = "lab_manual"  # 实训指导书
    OFFICIAL_DOC = "official_doc"  # 工具官方文档
    JOB_POSTING = "job_posting"  # 合法公开岗位信息


class EvidenceType(StrEnum):
    """两类证据必须分开——判分标准完全不同。"""

    DOCUMENTARY = "documentary"  # 文献证据：可溯源到 knowledge_chunk
    STATISTICAL = "statistical"  # 统计证据：可溯源到 job_posting 原文片段


class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"  # 触发「当前知识库暂无足够依据」


class LLMRunStatus(StrEnum):
    SUCCESS = "success"
    PARSE_FAILED = "parse_failed"  # 模型有响应但不符合 Schema
    PROVIDER_ERROR = "provider_error"  # 网络 / 鉴权 / 限流


class DataFlag(StrEnum):
    """演示数据必须可识别，前端据此显示角标。"""

    REAL = "REAL"
    DEMO = "DEMO"


class TaskDifficulty(StrEnum):
    """实训任务难度。对应高职学生的三个进阶层次。"""

    BEGINNER = "beginner"  # 入门：跟着步骤做
    INTERMEDIATE = "intermediate"  # 进阶：需要判断与取舍
    ADVANCED = "advanced"  # 挑战：贴近真实项目复杂度


class TaskStatus(StrEnum):
    DRAFT = "draft"  # AI 生成，待教师确认
    PUBLISHED = "published"  # 教师确认，可发给学生
    ARCHIVED = "archived"


class UserTestRole(StrEnum):
    """用户测试参与者角色；仅记录角色，不记录真实身份信息。"""

    TEACHER = "teacher"
    STUDENT = "student"


class UserTestSessionStatus(StrEnum):
    DRAFT = "draft"
    COMPLETED = "completed"


class UserTestOutcome(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ItemType(StrEnum):
    """题型。客观题可自动判分，主观题需 LLM 或教师评分。"""

    SINGLE = "single"  # 单选
    MULTI = "multi"  # 多选
    JUDGE = "judge"  # 判断
    SHORT = "short"  # 简答（需评分）
    CODE = "code"  # 代码（需评分）


#: 可确定性自动判分的题型。其余需要评分环节介入。
OBJECTIVE_ITEM_TYPES: frozenset["ItemType"] = frozenset()  # 见文件末尾赋值


class AssessmentType(StrEnum):
    DIAGNOSTIC = "diagnostic"  # 入门诊断
    TASK = "task"  # 实训任务评分
    RETEST = "retest"  # 学习后复测


class AssessmentStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    SCORED = "scored"


class ProfileSource(StrEnum):
    DIAGNOSTIC = "diagnostic"
    TASK = "task"
    MANUAL = "manual"
    MERGED = "merged"  # 多来源融合


class PathStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ARCHIVED = "archived"


class PathItemType(StrEnum):
    """学习项类型。"""

    KNOWLEDGE = "knowledge"  # 知识学习
    TASK = "task"  # 实训任务
    ASSESSMENT = "assessment"  # 复测
    PRACTICE = "practice"  # 自主练习


class Provenance(StrEnum):
    """内容来源，用于区分「AI 生成」与「人工确认」。"""

    LLM_DRAFTED = "llm_drafted"
    HUMAN_REVIEWED = "human_reviewed"
    HUMAN_AUTHORED = "human_authored"
    IMPORTED = "imported"


#: 在 ItemType 定义之后赋值，避免前向引用
OBJECTIVE_ITEM_TYPES = frozenset({ItemType.SINGLE, ItemType.MULTI, ItemType.JUDGE})
