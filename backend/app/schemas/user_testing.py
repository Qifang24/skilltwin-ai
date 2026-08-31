"""Phase 15 用户测试的 API 契约。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import UserTestOutcome, UserTestRole, UserTestSessionStatus


class UserTestScriptTaskRead(BaseModel):
    code: str
    title: str
    expected_result: str


class UserTestScriptRead(BaseModel):
    id: str
    name: str
    participant_role: UserTestRole
    description: str
    tasks: list[UserTestScriptTaskRead]


class CreateUserTestSessionRequest(BaseModel):
    participant_alias: str = Field(min_length=2, max_length=64)
    participant_role: UserTestRole
    script_id: str = Field(min_length=1, max_length=64)
    consent_confirmed: bool


class UpdateUserTestTaskRequest(BaseModel):
    actual_result: str = Field(min_length=2, max_length=2000)
    outcome: UserTestOutcome
    accuracy: int = Field(ge=1, le=5, description="预期结果达成度：1 很低，5 完全达成")
    ease_of_use: int = Field(ge=1, le=5, description="易用性：1 很困难，5 很容易")
    feedback: str | None = Field(default=None, max_length=2000)


class CompleteUserTestSessionRequest(BaseModel):
    overall_feedback: str | None = Field(default=None, max_length=3000)


class UserTestTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_code: str
    title: str
    expected_result: str
    order_index: int
    actual_result: str | None = None
    outcome: UserTestOutcome | None = None
    accuracy: int | None = None
    ease_of_use: int | None = None
    feedback: str | None = None


class UserTestSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    participant_alias: str
    participant_role: UserTestRole
    script_id: str
    status: UserTestSessionStatus
    consent_confirmed: bool
    overall_feedback: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    tasks: list[UserTestTaskRead] = Field(default_factory=list)


class UserTestReportTaskRead(BaseModel):
    task_code: str
    title: str
    response_count: int
    completion_rate: float | None = None
    average_accuracy: float | None = None
    average_ease_of_use: float | None = None
    feedback_samples: list[str] = Field(default_factory=list)


class UserTestReportRead(BaseModel):
    completed_sessions: int
    draft_sessions: int
    participant_roles: dict[str, int] = Field(default_factory=dict)
    task_records: int
    overall_completion_rate: float | None = None
    average_accuracy: float | None = None
    average_ease_of_use: float | None = None
    tasks: list[UserTestReportTaskRead] = Field(default_factory=list)
    overall_feedback_samples: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reasoning_summary: str
