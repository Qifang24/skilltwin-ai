"""个性化学习路径 API 契约。

路径顺序来自确定性计算；Agent 只负责阶段标题、说明与行动建议。
生成响应把 Agent 元数据与持久化路径分开，查询历史路径时不会伪造已经
丢失的检索上下文。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import EvidenceSufficiency, PathItemType, PathStatus
from app.schemas.common import SourceRef


class GenerateLearningPathRequest(BaseModel):
    job_id: str | None = Field(
        default=None,
        max_length=64,
        description="不传时使用学生的 target_job_id",
    )
    max_phases: int = Field(default=4, ge=1, le=8)


class UpdateLearningPathItemRequest(BaseModel):
    status: PathStatus
    note: str | None = Field(default=None, max_length=500)


class StartPathRetestRequest(BaseModel):
    item_count: int = Field(default=16, ge=4, le=60)


class StartPathRetestResponse(BaseModel):
    assessment_id: str
    student_id: str
    job_id: str
    notes: list[str] = Field(default_factory=list)


class LearningPathActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action: str
    previous_status: PathStatus | None = None
    new_status: PathStatus | None = None
    ref_type: str | None = None
    ref_id: str | None = None
    note: str | None = None
    created_at: datetime


class LearningPathProgressRead(BaseModel):
    total_items: int = 0
    completed_items: int = 0
    skipped_items: int = 0
    done_items: int = 0
    percent: int = Field(default=0, ge=0, le=100)

    @classmethod
    def from_statuses(cls, statuses: list[PathStatus]) -> "LearningPathProgressRead":
        completed = sum(status is PathStatus.COMPLETED for status in statuses)
        skipped = sum(status is PathStatus.SKIPPED for status in statuses)
        done = completed + skipped
        total = len(statuses)
        return cls(
            total_items=total,
            completed_items=completed,
            skipped_items=skipped,
            done_items=done,
            percent=round(done / total * 100) if total else 0,
        )


class LearningPathItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_index: int
    item_type: PathItemType
    title: str
    description: str | None = None
    ref_id: str | None = None
    skill_code: str | None = None
    status: PathStatus
    completed_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    activities: list[LearningPathActivityRead] = Field(default_factory=list)


class LearningPathPhaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_index: int
    title: str
    description: str | None = None
    target_skill_codes: list[str] = Field(default_factory=list)
    est_hours: float | None = None
    status: PathStatus
    ordering_note: str | None = None
    items: list[LearningPathItemRead] = Field(default_factory=list)
    progress: LearningPathProgressRead = Field(default_factory=LearningPathProgressRead)

    @model_validator(mode="after")
    def _compute_progress(self) -> "LearningPathPhaseRead":
        self.progress = LearningPathProgressRead.from_statuses(
            [item.status for item in self.items]
        )
        return self


class LearningPathRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    job_id: str
    profile_id: str | None = None
    graph_id: str | None = None
    title: str | None = None
    rationale: str | None = None
    status: PathStatus
    ordering_method: str | None = None
    warnings: list[str] = Field(default_factory=list)
    generation_run_id: str | None = None
    created_at: datetime
    updated_at: datetime
    phases: list[LearningPathPhaseRead] = Field(default_factory=list)
    progress: LearningPathProgressRead = Field(default_factory=LearningPathProgressRead)

    @model_validator(mode="after")
    def _compute_progress(self) -> "LearningPathRead":
        self.progress = LearningPathProgressRead.from_statuses(
            [item.status for phase in self.phases for item in phase.items]
        )
        return self


class LearningPathAdaptationRead(BaseModel):
    linked_item_id: str | None = None
    archived_path_id: str | None = None
    new_path_id: str | None = None
    recalculated: bool = False
    message: str = ""
    warnings: list[str] = Field(default_factory=list)


class GenerateLearningPathResponse(BaseModel):
    path: LearningPathRead
    reasoning_summary: str = ""
    sources: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.PARTIAL
    ai_generated: bool = True
    warnings: list[str] = Field(default_factory=list)
