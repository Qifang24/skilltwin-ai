"""真实用户测试记录（Phase 15）。

不存姓名、联系方式、学号或访客标识；参与者只用研究别名表示。删除会话会级联
删除任务观察记录，便于按用户请求清除测试数据。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.core.enums import UserTestOutcome, UserTestRole, UserTestSessionStatus, db_enum


class UserTestSession(Base, TimestampMixin):
    __tablename__ = "user_test_session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    participant_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    participant_role: Mapped[UserTestRole] = mapped_column(
        db_enum(UserTestRole, "user_test_role"), nullable=False
    )
    script_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[UserTestSessionStatus] = mapped_column(
        db_enum(UserTestSessionStatus, "user_test_session_status"),
        default=UserTestSessionStatus.DRAFT,
        nullable=False,
    )
    consent_confirmed: Mapped[bool] = mapped_column(nullable=False, default=False)
    overall_feedback: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tasks: Mapped[list["UserTestTaskRecord"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="UserTestTaskRecord.order_index"
    )

    __table_args__ = (
        Index("ix_user_test_session_status", "status", "created_at"),
        Index("ix_user_test_session_role", "participant_role", "created_at"),
    )


class UserTestTaskRecord(Base, TimestampMixin):
    __tablename__ = "user_test_task_record"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("user_test_session.id", ondelete="CASCADE"), nullable=False
    )
    task_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    actual_result: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[UserTestOutcome | None] = mapped_column(
        db_enum(UserTestOutcome, "user_test_outcome")
    )
    accuracy: Mapped[int | None] = mapped_column(Integer)
    ease_of_use: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)

    session: Mapped[UserTestSession] = relationship(back_populates="tasks")

    __table_args__ = (
        Index("ix_user_test_task_session", "session_id", "order_index"),
    )
