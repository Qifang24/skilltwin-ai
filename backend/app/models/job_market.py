"""岗位市场数据（Module 1a）。

三张表构成一条**可下钻的证据链**：

    job_posting          原始 JD 全文（不改写、不概括）
      └ job_posting_skill  抽出的技能 + 命中的**原文片段**
          └ skill_demand_snapshot  物化统计，图表只读这里

「Python 需求占 82%」必须能一路点回到某条 JD 的某段原文。
做不到这一点的百分比，本项目一律不展示。

统计表刻意分别记录真实样本与演示样本数量：演示数据混进统计
在结构上就藏不住，前端据此显示角标，避免拿假数据充场面。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.enums import DataFlag, db_enum


class JobPosting(Base, TimestampMixin):
    """一条公开岗位信息。

    raw_text 必须是**原样抄录**的岗位描述。一旦改写或概括，
    技能抽取的 evidence_span 就无法与原文对齐，证据链即断。
    """

    __tablename__ = "job_posting"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    company_type: Mapped[str | None] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(64))

    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    #: 原始薪资表述，如「8-12K·13薪」。解析不了就留原文，不猜
    salary_text: Mapped[str | None] = mapped_column(String(128))

    education_req: Mapped[str | None] = mapped_column(String(64))
    experience_req: Mapped[str | None] = mapped_column(String(64))

    #: 岗位描述全文，原样抄录
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # ---------- 来源与合规 ----------
    source_name: Mapped[str | None] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    license_note: Mapped[str | None] = mapped_column(Text)

    #: REAL / DEMO。演示数据必须可识别，绝不允许混入对外展示的统计
    data_flag: Mapped[DataFlag] = mapped_column(
        db_enum(DataFlag, "posting_data_flag"),
        default=DataFlag.DEMO,
        nullable=False,
    )
    #: 导入时是否执行过联系方式脱敏
    pii_scrubbed: Mapped[bool] = mapped_column(default=False, nullable=False)

    import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("job_import_batch.id", ondelete="SET NULL")
    )
    source_record_id: Mapped[str | None] = mapped_column(String(255))
    dedupe_hash: Mapped[str | None] = mapped_column(String(64))

    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    skills: Mapped[list["JobPostingSkill"]] = relationship(
        back_populates="posting", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_posting_job_flag", "job_id", "data_flag"),
        Index("ix_posting_collected", "collected_at"),
        Index("ix_posting_dedupe_hash", "dedupe_hash"),
    )

    def __repr__(self) -> str:
        return f"<JobPosting {self.id} {self.title} [{self.data_flag}]>"


class JobImportBatch(Base, TimestampMixin):
    """A staged import. Rows do not become postings until confirm succeeds."""

    __tablename__ = "job_import_batch"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(96), nullable=False)
    job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", nullable=False)
    field_mapping: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    headers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filtered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class JobImportRow(Base, TimestampMixin):
    __tablename__ = "job_import_row"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("job_import_batch.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    normalized_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    dedupe_hash: Mapped[str | None] = mapped_column(String(64))
    posting_id: Mapped[str | None] = mapped_column(String(96))

    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_job_import_row_number"),
        Index("ix_job_import_row_batch_status", "batch_id", "status"),
    )


class JobSkillCandidate(Base, TimestampMixin):
    """Unknown terms are quarantined here; they never enter canonical Skill automatically."""

    __tablename__ = "job_skill_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    posting_id: Mapped[str] = mapped_column(
        ForeignKey("job_posting.id", ondelete="CASCADE"), nullable=False
    )
    candidate_name: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_span: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    reviewed_skill_code: Mapped[str | None] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="SET NULL")
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (
        UniqueConstraint("posting_id", "candidate_name", name="uq_job_skill_candidate"),
    )


class JobPostingSkill(Base, TimestampMixin):
    """一条 JD 中命中的一个技能。

    evidence_span 是**原文片段**，不是模型的转述 —— 它让每个百分比
    都能点回原文核验。与技能抽取采用同一条铁律：抄不出原文就不入库。
    """

    __tablename__ = "job_posting_skill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    posting_id: Mapped[str] = mapped_column(
        ForeignKey("job_posting.id", ondelete="CASCADE"), nullable=False
    )
    skill_code: Mapped[str] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="RESTRICT"), nullable=False
    )

    evidence_span: Mapped[str] = mapped_column(Text, nullable=False)
    #: llm / rule —— 便于对比两种抽取方式的效果
    extractor: Mapped[str] = mapped_column(String(32), default="llm", nullable=False)
    extractor_version: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float)

    posting: Mapped[JobPosting] = relationship(back_populates="skills")

    __table_args__ = (
        UniqueConstraint("posting_id", "skill_code", name="uq_posting_skill"),
        Index("ix_posting_skill_code", "skill_code"),
    )

    def __repr__(self) -> str:
        return f"<JobPostingSkill {self.posting_id} → {self.skill_code}>"


class SkillDemandSnapshot(Base, TimestampMixin):
    """物化的技能需求统计。图表只读这张表。

    由 SQL/numpy 确定性计算得出，**LLM 不参与**。
    这是「LLM 只做生成与解释，不做统计与排序」这条铁律的落点。
    """

    __tablename__ = "skill_demand_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    skill_code: Mapped[str] = mapped_column(
        ForeignKey("skill.skill_code", ondelete="RESTRICT"), nullable=False
    )

    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: 提及该技能的岗位数
    posting_count: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 该窗口内的岗位总数 —— 前端必须把它作为样本量 N 显示出来
    total_postings: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency: Mapped[float] = mapped_column(Float, nullable=False)

    #: 样本构成。demo_posting_count > 0 时前端必须显示「含演示数据」角标
    real_posting_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    demo_posting_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "job_id", "skill_code", "window_start", "window_end", name="uq_demand_window"
        ),
        Index("ix_demand_job_freq", "job_id", "frequency"),
    )

    @property
    def is_demo_contaminated(self) -> bool:
        """统计里混有演示数据 —— 不得作为对外结论展示。"""
        return self.demo_posting_count > 0

    def __repr__(self) -> str:
        return (
            f"<SkillDemandSnapshot {self.skill_code} "
            f"{self.posting_count}/{self.total_postings}>"
        )
