"""学习型 AI Tutor：学生画像 + 当前任务 + RAG + 最近对话。"""
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.core.errors import NotFoundError, ValidationError
from app.core.llm import Message
from app.core.llm_runner import LLMRunner, get_runner
from app.models.student import SkillProfile, Student
from app.models.training import TrainingTask
from app.models.tutor import TutorConversation, TutorMessage
from app.rag.retriever import HybridRetriever
from app.schemas.common import SourceRef
from app.schemas.tutor import TutorChatResponse, TutorMessageRead
from app.services.citation_verification_service import (
    CitationClaim,
    CitationVerificationService,
)


class TutorService:
    def __init__(
        self,
        db: Session,
        runner: LLMRunner | None = None,
        retriever: HybridRetriever | None = None,
    ) -> None:
        self.db = db
        self.runner = runner or get_runner()
        self.retriever = retriever or HybridRetriever()

    def chat(
        self,
        student_id: str,
        *,
        job_id: str,
        message: str,
        task_id: str | None = None,
        conversation_id: str | None = None,
    ) -> TutorChatResponse:
        student = self.db.get(Student, student_id)
        if not student:
            raise NotFoundError(f"未找到学生：{student_id}")
        task = self.db.get(TrainingTask, task_id) if task_id else None
        if task_id and not task:
            raise NotFoundError(f"未找到实训任务：{task_id}")
        if task and task.job_id != job_id:
            raise ValidationError("当前实训任务与目标岗位不一致")
        conversation = self.db.get(TutorConversation, conversation_id) if conversation_id else None
        if conversation and conversation.student_id != student_id:
            raise ValidationError("会话不属于当前学生")
        if conversation and conversation.job_id != job_id:
            raise ValidationError("会话与目标岗位不一致")
        if conversation and conversation.task_id != task_id:
            raise ValidationError("会话与当前实训任务不一致")
        if conversation is None:
            conversation = TutorConversation(
                id=f"tutor_{uuid.uuid4().hex[:20]}",
                student_id=student_id,
                job_id=job_id,
                task_id=task_id,
                title=message[:60],
            )
            self.db.add(conversation)
            self.db.flush()
        self.db.add(TutorMessage(conversation_id=conversation.id, role="user", content=message))
        history_query = (
            select(TutorMessage)
            .where(TutorMessage.conversation_id == conversation.id)
            .order_by(TutorMessage.created_at.desc())
            .limit(6)
        )
        history = list(self.db.execute(history_query).scalars())[::-1]
        profile_query = (
            select(SkillProfile)
            .options(selectinload(SkillProfile.entries))
            .where(SkillProfile.student_id == student_id, SkillProfile.job_id == job_id)
            .order_by(SkillProfile.computed_at.desc())
            .limit(1)
        )
        profile = self.db.execute(profile_query).scalars().first()
        profile_text = (
            "暂无完成的能力画像"
            if not profile
            else "；".join(
                f"{entry.skill_code}:{entry.score:.0f}(置信度{entry.confidence:.2f})"
                for entry in profile.entries
            )
        )
        query = f"{task.title if task else ''} {message} {job_id}"
        try:
            chunks = self.retriever.search(self.db, query, top_n=4)
            sources = [chunk.to_source_ref(marker=f"S{i}") for i, chunk in enumerate(chunks, 1)]
        except Exception:
            sources = []
        source_text = "\n".join(f"[{s.marker}] {s.quote or ''}" for s in sources) or "（当前知识库暂无足够依据）"
        context = (
            f"学生画像：{profile_text}\n"
            f"当前任务：{task.title if task else '未选择任务'}\n"
            f"任务步骤：{task.steps if task else '—'}\n"
            f"知识库依据：\n{source_text}"
        )
        messages = [
            Message(
                role="system",
                content=(
                    "你是职业教育 AI Tutor。用简洁中文辅导，不编造操作或来源；"
                    "问题指向不明时先追问。优先结合当前任务与知识库依据。"
                ),
            ),
            Message(role="system", content=context),
            *[
                Message(
                    role=item.role if item.role in ("user", "assistant") else "user",
                    content=item.content,
                )
                for item in history
            ],
            Message(role="user", content=message),
        ]
        run = self.runner.run(
            self.db,
            agent="ai_tutor",
            messages=messages,
            input_summary={
                "student_id": student_id,
                "job_id": job_id,
                "task_id": task_id,
                "conversation_id": conversation.id,
            },
            temperature=0.2,
            max_tokens=600,
            json_mode=False,
        )
        answer = run.text.strip() or "我暂时没有生成有效回答，请换一种说法再试。"
        verification = CitationVerificationService(self.db).verify_and_record(
            llm_run_id=run.llm_run_id,
            sources=sources,
            claims=[CitationClaim(text="AI Tutor 对学习问题的回答")],
        )
        assistant_message = TutorMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            sources=[source.model_dump(mode="json") for source in verification.sources],
            llm_run_id=run.llm_run_id,
        )
        self.db.add(assistant_message)
        self.db.commit()
        return TutorChatResponse(
            conversation_id=conversation.id,
            answer=TutorMessageRead(
                id=assistant_message.id,
                role="assistant",
                content=answer,
                sources=verification.sources,
                created_at=assistant_message.created_at,
            ),
            reasoning_summary=(
                f"结合当前任务、最近对话、学生画像和 {len(verification.sources)} 条已核验知识库依据回答。"
            ),
            confidence=verification.confidence,
            evidence_sufficiency=verification.evidence_sufficiency,
            warnings=verification.warnings,
        )
