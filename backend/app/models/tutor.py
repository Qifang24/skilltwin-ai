"""AI Tutor 的会话与消息记忆（Phase 13）。"""
from __future__ import annotations

from typing import Any
from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base, TimestampMixin


class TutorConversation(Base, TimestampMixin):
    __tablename__ = "tutor_conversation"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("training_task.id", ondelete="SET NULL"))
    title: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (Index("ix_tutor_conversation_student", "student_id", "updated_at"),)


class TutorMessage(Base, TimestampMixin):
    __tablename__ = "tutor_message"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("tutor_conversation.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(MutableList.as_mutable(JSON), default=list, nullable=False)
    llm_run_id: Mapped[str | None] = mapped_column(ForeignKey("llm_run.id", ondelete="SET NULL"))
    __table_args__ = (Index("ix_tutor_message_conversation", "conversation_id", "created_at"),)
