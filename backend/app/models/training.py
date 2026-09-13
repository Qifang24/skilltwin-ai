"""实训任务（Module 3）。

把岗位真实工作任务转化为教学任务。设计上刻意**全部结构化**而非一段
Markdown 文本：只有结构化了，才能做到
  - 前端按区块渲染（学习目标 / 步骤 / 评分标准分开展示）
  - 评分量规能被 Phase 8 的测评环节直接读取，回写学生能力画像
  - 教师可以只改其中一步，而不是重写整篇

任务通过 source_node_id 挂在能力图谱节点上，
通过 training_task_skill 关联到规范技能 —— 于是「这个实训练的是哪几项能力」
是可查询的事实，而不是教师的口头说明。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.enums import TaskDifficulty, TaskStatus, db_enum


class TrainingTask(Base, TimestampMixin):
    __tablename__ = "training_task"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    #: 来源能力节点。任务由哪项能力派生，可追溯
    source_node_id: Mapped[str | None] = mapped_column(
        ForeignKey("competency_node.id", ondelete="SET NULL")
    )
    #: 可选的培养方案与课程来源。旧任务可以为空；一旦教师从培养方案
    #: 发起生成，就把选择保存为稳定外键，避免只在 prompt 中出现而无法追溯。
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("curriculum_plan.id", ondelete="RESTRICT")
    )
    course_id: Mapped[str | None] = mapped_column(
        ForeignKey("curriculum_course.id", ondelete="RESTRICT")
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: 工作情境：把学生放进真实岗位场景，而不是「请完成以下练习」
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[TaskDifficulty] = mapped_column(
        db_enum(TaskDifficulty, "task_difficulty"),
        default=TaskDifficulty.BEGINNER,
        nullable=False,
    )
    est_minutes: Mapped[int | None] = mapped_column(Integer)

    # ---------- 结构化正文 ----------
    #: [{"text": "...", "skill_code": "..."}]
    objectives: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    #: [{"order": 1, "title": "...", "detail": "...", "hint": "..."}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    #: 提交成果 ["标注结果文件(JSON)", "质量自检报告"]
    deliverables: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    #: 评分量规 [{"dimension":"标注准确率","weight":40,"levels":[...]}]
    #: Phase 8 的测评会直接读它来回写学生能力画像
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    #: 常见错误 [{"mistake":"...","consequence":"...","fix":"..."}]
    common_mistakes: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    extensions: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    safety_notes: Mapped[str | None] = mapped_column(Text)

    # ---------- 溯源与状态 ----------
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), default=list, nullable=False
    )
    generation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("llm_run.id", ondelete="SET NULL")
    )
    status: Mapped[TaskStatus] = mapped_column(
        db_enum(TaskStatus, "task_status"), default=TaskStatus.DRAFT, nullable=False
    )
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    edited_by_human: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    published_by: Mapped[str | None] = mapped_column(String(128))

    skills: Mapped[list["TrainingTaskSkill"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_task_job_status", "job_id", "status"),
        Index("ix_task_source_node", "source_node_id"),
        Index("ix_task_plan", "plan_id"),
        Index("ix_task_course", "course_id"),
    )

    def __repr__(self) -> str:
        return f"<TrainingTask {self.id} {self.title}>"


class TrainingTaskSkill(Base, TimestampMixin):
    """任务训练哪些技能、要求达到什么程度。

    weight 用于 Phase 8：学生完成任务后，rubric 得分按此权重
    分配回各技能，更新能力画像。
    """

    __tablename__ = "training_task_skill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("training_task.id", ondelete="CASCADE"), nullable=False
    )
    skill_code: Mapped[str] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="RESTRICT"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    target_level: Mapped[int | None] = mapped_column(Integer)

    task: Mapped[TrainingTask] = relationship(back_populates="skills")

    __table_args__ = (
        UniqueConstraint("task_id", "skill_code", name="uq_task_skill"),
        Index("ix_task_skill_code", "skill_code"),
    )

    def __repr__(self) -> str:
        return f"<TrainingTaskSkill {self.task_id} → {self.skill_code}>"
