"""实训任务 Schema。

全部结构化而非一段 Markdown —— 这是刻意的：
只有结构化了，评分量规才能被后续测评环节直接读取并回写学生能力画像，
教师也才能只改其中一步而不必重写整篇。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import TaskDifficulty, TaskStatus
from app.schemas.common import SourceRef


class TaskObjective(BaseModel):
    text: str = Field(min_length=4, max_length=200)
    #: 对应的规范技能编码，由服务端校验
    skill_code: str | None = Field(default=None, max_length=96)


class TaskStep(BaseModel):
    order: int = Field(ge=1, le=20)
    title: str = Field(min_length=2, max_length=120)
    detail: str = Field(min_length=10, max_length=1000)
    #: 给学生的提示，不是答案
    hint: str | None = Field(default=None, max_length=300)


class RubricLevel(BaseModel):
    level: str = Field(max_length=32, description="如 优秀 / 合格 / 待改进")
    criteria: str = Field(min_length=4, max_length=400)


class RubricDimension(BaseModel):
    dimension: str = Field(min_length=2, max_length=80)
    weight: int = Field(ge=5, le=100, description="百分制权重")
    levels: list[RubricLevel] = Field(min_length=2, max_length=4)


class CommonMistake(BaseModel):
    mistake: str = Field(min_length=4, max_length=200)
    consequence: str = Field(min_length=4, max_length=300)
    fix: str = Field(min_length=4, max_length=300)


class TrainingTaskDraft(BaseModel):
    """LLM 输出的任务草案。"""

    title: str = Field(min_length=4, max_length=120)
    #: 工作情境：把学生放进真实岗位场景
    scenario: str = Field(min_length=20, max_length=800)
    difficulty: TaskDifficulty = TaskDifficulty.BEGINNER
    est_minutes: int = Field(default=90, ge=15, le=960)

    objectives: list[TaskObjective] = Field(min_length=2, max_length=8)
    steps: list[TaskStep] = Field(min_length=3, max_length=12)
    deliverables: list[str] = Field(min_length=1, max_length=8)
    rubric: list[RubricDimension] = Field(min_length=2, max_length=6)
    common_mistakes: list[CommonMistake] = Field(default_factory=list, max_length=6)
    extensions: list[str] = Field(default_factory=list, max_length=4)
    safety_notes: str | None = Field(default=None, max_length=600)


# ============================================================ 读取视图
class TaskSkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_code: str
    weight: float
    target_level: int | None = None
    skill_name: str | None = None


class TrainingTaskSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    source_node_id: str | None = None
    plan_id: str | None = None
    course_id: str | None = None
    title: str
    difficulty: TaskDifficulty
    est_minutes: int | None = None
    status: TaskStatus
    ai_generated: bool
    edited_by_human: bool
    published_by: str | None = None
    skill_count: int = 0


class TaskCurriculumPlanRead(BaseModel):
    """任务关联的培养方案快照视图（数据仍以方案表为准）。"""

    id: str
    name: str
    profession: str | None = None
    version: str | None = None
    source_name: str
    source_url: str | None = None
    is_partial: bool


class TaskCurriculumCourseRead(BaseModel):
    """任务关联课程的教学上下文。"""

    id: str
    plan_id: str
    course_code: str | None = None
    name: str
    category: str | None = None
    total_hours: int | None = None
    objectives: str | None = None
    description: str | None = None
    teaching_content: str | None = None
    knowledge_points: str | None = None
    practical_content: str | None = None
    learning_outcomes: str | None = None


class TaskCourseEvidenceRead(BaseModel):
    """课程原文或课程—技能映射中的可核验证据。"""

    evidence_type: str = Field(description="course_source | course_field | skill_coverage")
    field: str | None = None
    skill_code: str | None = None
    chunk_id: str | None = None
    page: str | None = None
    quote: str
    is_generation_snapshot: bool = False


class TrainingTaskDetail(TrainingTaskSummary):
    scenario: str
    objectives: list[dict] = Field(default_factory=list)
    steps: list[dict] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    rubric: list[dict] = Field(default_factory=list)
    common_mistakes: list[dict] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    safety_notes: str | None = None
    citations: list[dict] = Field(default_factory=list)
    skills: list[TaskSkillRead] = Field(default_factory=list)
    generation_run_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    #: 来源能力节点名称，便于展示「本任务由哪项能力派生」
    source_node_name: str | None = None
    curriculum_plan: TaskCurriculumPlanRead | None = None
    curriculum_course: TaskCurriculumCourseRead | None = None
    course_evidence: list[TaskCourseEvidenceRead] = Field(default_factory=list)


class GenerateTaskRequest(BaseModel):
    #: 能力图谱中的节点 id，通常是 competency_unit
    node_id: str = Field(min_length=1, max_length=160)
    difficulty: TaskDifficulty = TaskDifficulty.BEGINNER
    #: 可选的情境要求，如「结合自动驾驶道路场景」
    context: str | None = Field(default=None, max_length=200)
    #: 两项均为可选，保证旧客户端只提交 node_id 的请求继续可用。
    #: 只选择课程时，服务端会从课程记录推导 plan_id。
    plan_id: str | None = Field(default=None, min_length=1, max_length=96)
    course_id: str | None = Field(default=None, min_length=1, max_length=128)


class PublishTaskRequest(BaseModel):
    published_by: str = Field(min_length=1, max_length=128)


class TaskSkillUpdate(BaseModel):
    skill_code: str = Field(min_length=1, max_length=96)
    weight: float = Field(ge=0, le=1)
    target_level: int | None = Field(default=None, ge=1, le=4)


class UpdateTrainingTaskRequest(TrainingTaskDraft):
    """教师可修改任务的全部教学内容；发布状态保持不变。"""

    skills: list[TaskSkillUpdate] = Field(min_length=1, max_length=20)


class TaskGenerationSources(BaseModel):
    sources: list[SourceRef] = Field(default_factory=list)
