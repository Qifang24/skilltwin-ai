"""测评与能力画像 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import AssessmentStatus, AssessmentType, ItemType, ProfileSource
from app.schemas.learning import LearningPathAdaptationRead


# ======================================================== 出题（LLM 输出）
class ItemOption(BaseModel):
    key: str = Field(pattern=r"^[A-F]$")
    text: str = Field(min_length=1, max_length=300)


class GeneratedItem(BaseModel):
    stem: str = Field(min_length=8, max_length=600)
    item_type: ItemType
    options: list[ItemOption] = Field(default_factory=list, max_length=6)
    answer_key: list[str] = Field(min_length=1, max_length=6)
    explanation: str = Field(min_length=4, max_length=600)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    #: 该题主要考查的技能，必须来自给定的技能表
    skill_code: str = Field(min_length=1, max_length=96)
    #: 引用的依据编号，如 ["S1"]
    evidence_markers: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("item_type")
    @classmethod
    def _only_objective(cls, v: ItemType) -> ItemType:
        """诊断测评只出可自动判分的客观题。

        主观题需要人工或模型评分，会引入额外的不确定性；
        诊断阶段的目的是快速定位能力短板，客观题足够且判分确定。
        """
        if v not in (ItemType.SINGLE, ItemType.MULTI, ItemType.JUDGE):
            raise ValueError(f"诊断测评暂只支持客观题，收到 {v.value}")
        return v

    @field_validator("answer_key")
    @classmethod
    def _keys_are_clean(cls, v: list[str]) -> list[str]:
        return [k.strip().upper() if len(k.strip()) == 1 else k.strip().lower() for k in v]


class ItemBatch(BaseModel):
    items: list[GeneratedItem] = Field(min_length=1, max_length=10)


# ============================================================ 读取视图
class ItemRead(BaseModel):
    """发给学生的题目视图 —— **不含答案**。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    stem: str
    item_type: ItemType
    options: list[dict] = Field(default_factory=list)
    difficulty: float
    skill_codes: list[str] = Field(default_factory=list)


class ItemReveal(ItemRead):
    """交卷后的视图，含答案与解析。"""

    answer_key: list[str] = Field(default_factory=list)
    explanation: str | None = None
    source_ref: list[dict] = Field(default_factory=list)


class StudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    target_job_id: str | None = None
    cohort: str | None = None
    created_at: datetime


class CreateStudentRequest(BaseModel):
    #: 化名。**不要填真实姓名** —— 系统不存储个人身份信息
    display_name: str = Field(min_length=1, max_length=64)
    target_job_id: str | None = Field(default=None, max_length=64)
    cohort: str | None = Field(default=None, max_length=64)


class StartAssessmentRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    type: AssessmentType = AssessmentType.DIAGNOSTIC
    #: 题量。太少则能力估计不可信，太多学生做不完
    item_count: int = Field(default=16, ge=4, le=60)


class AssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    job_id: str
    type: AssessmentType
    status: AssessmentStatus
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    items: list[ItemRead] = Field(default_factory=list)
    #: 开考前的统计效力提示，例如题量相对技能数偏少
    notes: list[str] = Field(default_factory=list)


class ResponseInput(BaseModel):
    item_id: str = Field(min_length=1, max_length=96)
    response: list[str] = Field(default_factory=list)


class SubmitAssessmentRequest(BaseModel):
    responses: list[ResponseInput] = Field(min_length=1, max_length=100)


# ============================================================ 能力画像
class ProfileEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_code: str
    skill_name: str | None = None
    category: str | None = None
    score: float
    score_low: float
    score_high: float
    confidence: float
    evidence_count: float
    method: str
    #: 置信度不足时前端应显示区间而非点估计
    reliable: bool = False


class SkillProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    job_id: str | None = None
    source: ProfileSource
    assessment_id: str | None = None
    computed_at: datetime | None = None
    entries: list[ProfileEntryRead] = Field(default_factory=list)
    #: 整体提示，如「本次仅 12 题，多数维度证据不足」
    notes: list[str] = Field(default_factory=list)


class GapRead(BaseModel):
    skill_code: str
    skill_name: str | None = None
    category: str | None = None
    target_score: float
    current_score: float
    gap: float
    confidence: float
    evidence_count: float
    reliable: bool
    #: 该技能尚未被任何题目考查
    untested: bool = False


class SkillGapReport(BaseModel):
    student_id: str
    job_id: str
    graph_id: str | None = None
    profile_id: str | None = None
    gaps: list[GapRead] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SubmitResult(BaseModel):
    assessment_id: str
    profile_id: str
    correct_count: int
    total_count: int
    #: 本次测评实际更新了哪些技能
    updated_skill_codes: list[str] = Field(default_factory=list)
    #: 为保持完整向量而从上一份同岗位画像继承了哪些技能
    inherited_skill_codes: list[str] = Field(default_factory=list)
    learning_path_update: LearningPathAdaptationRead | None = None
    profile: SkillProfileRead
