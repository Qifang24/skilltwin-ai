from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.core.enums import ProfileSource, SkillCategory, SourceType, TaskDifficulty, TaskStatus
from app.core.llm import EchoProvider
from app.core.llm_runner import LLMRunner
from app.models.ontology import Job, Skill
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.models.student import SkillProfile, SkillProfileEntry, Student
from app.models.training import TrainingTask
from app.models.tutor import TutorMessage
from app.schemas.common import SourceRef
from app.services.tutor_service import TutorService


class FakeChunk:
    def to_source_ref(self, marker: str) -> SourceRef:
        return SourceRef(type="documentary", marker=marker, chunk_id="doc#1", source_name="测试标准", page="3", quote="数据清洗应保留可核验记录。")


class FakeRetriever:
    def search(self, *_args, **_kwargs):
        return [FakeChunk()]


@pytest.fixture
def tutor_context(db: Session) -> Session:
    db.add(Job(id="ai_data_annotator", name="AI数据标注工程师"))
    db.add(Skill(skill_code="data.cleaning", name_zh="数据清洗", category=SkillCategory.DATA))
    db.flush()
    db.add(Student(id="student_a", display_name="学生A", target_job_id="ai_data_annotator"))
    db.add(KnowledgeDoc(id="doc", title="测试标准", source_name="测试标准", source_type=SourceType.INDUSTRY_SPEC))
    db.add(KnowledgeChunk(id="doc#1", doc_id="doc", chunk_index=1, text="数据清洗应保留可核验记录。"))
    db.add(TrainingTask(id="task_a", job_id="ai_data_annotator", title="道路数据清洗", scenario="场景", difficulty=TaskDifficulty.BEGINNER, objectives=[], steps=[{"order": 1, "detail": "检查空值"}], deliverables=[], rubric=[], common_mistakes=[], extensions=[], citations=[], status=TaskStatus.PUBLISHED))
    db.flush()
    db.add(SkillProfile(id="profile_a", student_id="student_a", job_id="ai_data_annotator", source=ProfileSource.DIAGNOSTIC, entries=[SkillProfileEntry(skill_code="data.cleaning", score=40, score_low=20, score_high=60, confidence=.3, evidence_count=1)]))
    db.commit()
    return db


def test_tutor_uses_context_and_persists_memory(tutor_context: Session) -> None:
    provider = EchoProvider(scripted=["先检查空值，再记录处理规则。"])
    service = TutorService(tutor_context, runner=LLMRunner(provider=provider), retriever=FakeRetriever())
    response = service.chat("student_a", job_id="ai_data_annotator", task_id="task_a", message="这一步怎么做？")
    assert response.answer.content.startswith("先检查")
    assert response.answer.sources[0].chunk_id == "doc#1"
    prompt = "\n".join(message.content for message in provider.calls[0])
    assert "这一步怎么做？" in prompt and "道路数据清洗" in prompt and "data.cleaning:40" in prompt
    messages = tutor_context.query(TutorMessage).all()
    assert [item.role for item in messages] == ["user", "assistant"]


def test_tutor_rejects_other_students_conversation(tutor_context: Session) -> None:
    service = TutorService(tutor_context, runner=LLMRunner(provider=EchoProvider(scripted=["答复"])), retriever=FakeRetriever())
    conversation = service.chat("student_a", job_id="ai_data_annotator", message="你好").conversation_id
    tutor_context.add(Student(id="student_b", display_name="学生B", target_job_id="ai_data_annotator")); tutor_context.commit()
    with pytest.raises(Exception, match="会话不属于"):
        service.chat("student_b", job_id="ai_data_annotator", message="读取", conversation_id=conversation)


def test_tutor_rejects_conversation_for_another_job(tutor_context: Session) -> None:
    service = TutorService(tutor_context, runner=LLMRunner(provider=EchoProvider(scripted=["答复"])), retriever=FakeRetriever())
    conversation = service.chat("student_a", job_id="ai_data_annotator", message="你好").conversation_id
    with pytest.raises(Exception, match="会话与目标岗位不一致"):
        service.chat("student_a", job_id="another_job", message="读取", conversation_id=conversation)


def test_tutor_rejects_conversation_for_another_task(tutor_context: Session) -> None:
    tutor_context.add(TrainingTask(id="task_b", job_id="ai_data_annotator", title="另一项任务", scenario="场景", difficulty=TaskDifficulty.BEGINNER, objectives=[], steps=[{"order": 1, "detail": "检查空值"}], deliverables=[], rubric=[], common_mistakes=[], extensions=[], citations=[], status=TaskStatus.PUBLISHED))
    tutor_context.commit()
    service = TutorService(tutor_context, runner=LLMRunner(provider=EchoProvider(scripted=["答复"])), retriever=FakeRetriever())
    conversation = service.chat("student_a", job_id="ai_data_annotator", task_id="task_a", message="你好").conversation_id
    with pytest.raises(Exception, match="会话与当前实训任务不一致"):
        service.chat("student_a", job_id="ai_data_annotator", task_id="task_b", message="读取", conversation_id=conversation)
