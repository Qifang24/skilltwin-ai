"""Phase 9A：个性化学习路径生成、持久化与 API 测试。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

import app.services.learning_path_service as learning_module
from app.agents.learning_path import LearningPathAgent
from app.core.config import DemoMode
from app.core.db import utcnow
from app.core.enums import (
    EdgeRelation,
    EvidenceType,
    GraphStatus,
    ItemType,
    NodeType,
    PathItemType,
    PathStatus,
    SkillCategory,
    TaskDifficulty,
    TaskStatus,
)
from app.core.errors import ValidationError
from app.core.llm import EchoProvider
from app.core.llm_runner import LLMRunner
from app.models.competency import CompetencyEdge, CompetencyGraph, CompetencyNode
from app.models.ontology import Job, Skill
from app.models.learning import LearningPathActivity
from app.models.student import (
    AssessmentItem,
    AssessmentItemSkill,
    SkillProfile,
    SkillProfileEntry,
    Student,
)
from app.models.training import TrainingTask, TrainingTaskSkill
from app.schemas.common import SourceRef
from app.services.learning_path_service import LearningPathService


class OfflineLearningPathAgent(LearningPathAgent):
    """测试只验证业务编排，不加载本地 RAG 索引。"""

    def retrieve(self, db: Session, inp):  # noqa: ANN001
        return []


def _copy_json() -> str:
    return json.dumps(
        {
            "title": "AI数据标注工程师个性化成长路径",
            "rationale": "先补齐基础标注能力，再进入质量审核训练，阶段顺序来自能力前置关系。",
            "phases": [
                {
                    "order_index": 0,
                    "title": "夯实视觉标注基础",
                    "description": "先掌握视觉数据标注规范，为后续质量审核建立必要基础。",
                    "est_hours": 8,
                    "suggestions": [
                        "完成一组图像标注练习并逐项自检",
                        "对照标注规范记录三类常见错误",
                    ],
                },
                {
                    "order_index": 1,
                    "title": "强化标注质量审核",
                    "description": "在标注基础稳定后练习质量审核，形成发现并修正问题的能力。",
                    "est_hours": 10,
                    "suggestions": [
                        "使用评分量规复核一批标注结果",
                        "整理审核发现并形成质量改进清单",
                    ],
                },
            ],
        },
        ensure_ascii=False,
    )


def _agent() -> OfflineLearningPathAgent:
    return OfflineLearningPathAgent(
        runner=LLMRunner(
            provider=EchoProvider([_copy_json()]), demo_mode=DemoMode.LIVE
        )
    )


def test_learning_path_agent_receives_retrieved_evidence() -> None:
    agent = _agent()
    messages = agent.render_prompt(
        learning_module.PathCopyInput(
            student_name="学生A",
            job_name="AI数据标注工程师",
            ordering_method="topological+gap_desc",
            phases=[(0, [("视觉数据标注", 30, True)], "无前置依赖")],
        ),
        [
            SourceRef(
                type=EvidenceType.DOCUMENTARY,
                marker="S1",
                chunk_id="doc#1",
                source_name="测试标准",
                quote="标注结果应按规范完成质量检查。",
                verified=True,
            )
        ],
    )
    prompt = messages[-1].content
    assert "[S1]" in prompt
    assert "标注结果应按规范完成质量检查" in prompt


@pytest.fixture
def path_context(db: Session) -> Session:
    db.add(Job(id="ai_data_annotator", name="AI数据标注工程师"))
    db.add_all(
        [
            Skill(
                skill_code="annot.image",
                name_zh="视觉数据标注",
                category=SkillCategory.ANNOTATION,
            ),
            Skill(
                skill_code="quality.audit",
                name_zh="标注数据审核",
                category=SkillCategory.QUALITY,
            ),
            Skill(
                skill_code="tool.cvat",
                name_zh="CVAT 使用",
                category=SkillCategory.TOOL,
            ),
        ]
    )
    db.add(
        Student(
            id="stu_path",
            display_name="学生A",
            target_job_id="ai_data_annotator",
        )
    )
    db.add(
        CompetencyGraph(
            id="graph_path",
            job_id="ai_data_annotator",
            version=1,
            status=GraphStatus.APPROVED,
            title="AI数据标注工程师能力图谱",
        )
    )
    db.add_all(
        [
            CompetencyNode(
                id="graph_path.annot",
                graph_id="graph_path",
                node_type=NodeType.SKILL_POINT,
                name="视觉数据标注",
                skill_code="annot.image",
                mastery_level=2,
            ),
            CompetencyNode(
                id="graph_path.audit",
                graph_id="graph_path",
                node_type=NodeType.SKILL_POINT,
                name="标注数据审核",
                skill_code="quality.audit",
                mastery_level=3,
            ),
            CompetencyNode(
                id="graph_path.cvat",
                graph_id="graph_path",
                node_type=NodeType.SKILL_POINT,
                name="CVAT 使用",
                skill_code="tool.cvat",
                mastery_level=3,
            ),
        ]
    )
    db.commit()

    db.add(
        CompetencyEdge(
            graph_id="graph_path",
            from_node_id="graph_path.annot",
            to_node_id="graph_path.audit",
            relation=EdgeRelation.PREREQ,
        )
    )
    profile = SkillProfile(
        id="profile_path",
        student_id="stu_path",
        job_id="ai_data_annotator",
        computed_at=utcnow(),
    )
    db.add(profile)
    db.flush()
    db.add_all(
        [
            SkillProfileEntry(
                profile_id=profile.id,
                skill_code="annot.image",
                score=20,
                score_low=10,
                score_high=35,
                confidence=0.75,
                evidence_count=6,
                method="wilson",
            ),
            SkillProfileEntry(
                profile_id=profile.id,
                skill_code="quality.audit",
                score=10,
                score_low=4,
                score_high=25,
                confidence=0.8,
                evidence_count=6,
                method="wilson",
            ),
        ]
    )
    task = TrainingTask(
        id="task_audit",
        job_id="ai_data_annotator",
        title="标注质量审核实训",
        scenario="你需要审核一批视觉标注结果并形成质量报告。",
        difficulty=TaskDifficulty.BEGINNER,
        est_minutes=90,
        status=TaskStatus.PUBLISHED,
    )
    db.add(task)
    db.flush()
    db.add(
        TrainingTaskSkill(
            task_id=task.id,
            skill_code="quality.audit",
            weight=1.0,
            target_level=3,
        )
    )
    db.commit()
    return db


def test_generate_persists_ordered_path_and_real_task(path_context: Session) -> None:
    service = LearningPathService(path_context)
    generated = service.generate_for_student(
        student_id="stu_path", agent=_agent()
    )
    path_context.commit()

    loaded = service.latest_path("stu_path", "ai_data_annotator")
    assert loaded is not None
    assert loaded.id == generated.path.id
    assert [p.target_skill_codes for p in loaded.phases] == [
        ["annot.image"],
        ["quality.audit"],
    ]
    assert any("尚未被测评" in warning for warning in loaded.warnings)

    first_types = {item.item_type for item in loaded.phases[0].items}
    assert PathItemType.PRACTICE in first_types
    assert PathItemType.KNOWLEDGE in first_types
    assert PathItemType.ASSESSMENT in first_types

    task_items = [
        item
        for phase in loaded.phases
        for item in phase.items
        if item.item_type is PathItemType.TASK
    ]
    assert [item.ref_id for item in task_items] == ["task_audit"]


def test_untested_skill_is_not_treated_as_zero_score(path_context: Session) -> None:
    generated = LearningPathService(path_context).generate_for_student(
        student_id="stu_path", agent=_agent()
    )
    path_context.commit()

    planned = {
        code
        for phase in generated.path.phases
        for code in phase.target_skill_codes
    }
    assert "tool.cvat" not in planned
    assert any("尚未被测评" in warning for warning in generated.warnings)


def test_regeneration_archives_previous_path(path_context: Session) -> None:
    service = LearningPathService(path_context)
    first = service.generate_for_student(student_id="stu_path", agent=_agent()).path
    path_context.commit()
    second = service.generate_for_student(student_id="stu_path", agent=_agent()).path
    path_context.commit()

    path_context.refresh(first)
    assert first.status is PathStatus.ARCHIVED
    assert second.status is PathStatus.ACTIVE
    assert service.latest_path("stu_path", "ai_data_annotator").id == second.id


def test_generation_requires_profile_for_target_job(path_context: Session) -> None:
    path_context.add(
        Student(
            id="stu_no_profile",
            display_name="学生B",
            target_job_id="ai_data_annotator",
        )
    )
    path_context.commit()

    with pytest.raises(ValidationError, match="尚未完成目标岗位的诊断测评"):
        LearningPathService(path_context).generate_for_student(
            student_id="stu_no_profile", agent=_agent()
        )


def test_generation_rejects_profile_with_only_untested_targets(
    path_context: Session,
) -> None:
    profile = path_context.get(SkillProfile, "profile_path")
    for entry in list(profile.entries):
        path_context.delete(entry)
    path_context.commit()
    path_context.expire_all()

    with pytest.raises(ValidationError) as exc_info:
        LearningPathService(path_context).generate_for_student(
            student_id="stu_path", agent=_agent()
        )
    warnings = exc_info.value.detail["warnings"]
    assert any("尚未被测评" in warning for warning in warnings)


def test_learning_path_generate_and_latest_api(
    path_context: Session, client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(learning_module, "LearningPathAgent", lambda: _agent())

    created = client.post(
        "/api/v1/students/stu_path/learning-paths/generate",
        json={"max_phases": 4},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["path"]["student_id"] == "stu_path"
    assert len(body["path"]["phases"]) == 2
    assert body["ai_generated"] is True
    assert body["confidence"] == 0.315  # 无可核验来源时会下调
    assert any("尚未被测评" in warning for warning in body["warnings"])

    latest = client.get(
        "/api/v1/students/stu_path/learning-paths/latest",
        params={"job_id": "ai_data_annotator"},
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == body["path"]["id"]


def test_latest_path_returns_404_when_absent(path_context: Session, client) -> None:
    response = client.get("/api/v1/students/stu_path/learning-paths/latest")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_item_status_updates_activity_and_progress(
    path_context: Session, client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(learning_module, "LearningPathAgent", lambda: _agent())
    created = client.post(
        "/api/v1/students/stu_path/learning-paths/generate",
        json={"max_phases": 4},
    )
    assert created.status_code == 201, created.text
    path = created.json()["path"]
    knowledge = next(
        item
        for phase in path["phases"]
        for item in phase["items"]
        if item["item_type"] == "knowledge"
    )

    updated = client.patch(
        f"/api/v1/students/stu_path/learning-path-items/{knowledge['id']}",
        json={"status": "completed", "note": "已阅读规范并完成自检"},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["progress"]["completed_items"] == 1
    changed = next(
        item
        for phase in body["phases"]
        for item in phase["items"]
        if item["id"] == knowledge["id"]
    )
    assert changed["status"] == "completed"
    assert changed["completed_at"] is not None
    assert changed["activities"][-1]["action"] == "status_changed"
    assert changed["activities"][-1]["note"] == "已阅读规范并完成自检"

    # 学习项完成只记进度，不凭空制造新的能力画像。
    assert path_context.query(SkillProfile).count() == 1


def test_assessment_item_cannot_be_completed_manually(
    path_context: Session, client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(learning_module, "LearningPathAgent", lambda: _agent())
    path = client.post(
        "/api/v1/students/stu_path/learning-paths/generate",
        json={"max_phases": 4},
    ).json()["path"]
    retest = next(
        item
        for phase in path["phases"]
        for item in phase["items"]
        if item["item_type"] == "assessment"
    )

    response = client.patch(
        f"/api/v1/students/stu_path/learning-path-items/{retest['id']}",
        json={"status": "completed"},
    )
    assert response.status_code == 409
    assert "必须完成判分" in response.json()["error"]["message"]


def test_path_becomes_completed_when_all_items_are_done(
    path_context: Session, client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(learning_module, "LearningPathAgent", lambda: _agent())
    path = client.post(
        "/api/v1/students/stu_path/learning-paths/generate",
        json={"max_phases": 4},
    ).json()["path"]

    latest = path
    for phase in path["phases"]:
        for item in phase["items"]:
            latest = client.patch(
                f"/api/v1/students/stu_path/learning-path-items/{item['id']}",
                json={
                    "status": (
                        "skipped" if item["item_type"] == "assessment" else "completed"
                    )
                },
            ).json()

    assert latest["status"] == "completed"
    assert latest["progress"]["percent"] == 100
    assert latest["progress"]["done_items"] == latest["progress"]["total_items"]
    assert all(phase["status"] == "completed" for phase in latest["phases"])


def test_linked_retest_archives_old_path_and_recalculates(
    path_context: Session, client, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(4):
        item = AssessmentItem(
            id=f"retest_item_{index}",
            job_id="ai_data_annotator",
            stem=f"视觉标注复测题目 {index}：以下做法是否符合规范？",
            item_type=ItemType.SINGLE,
            options=[{"key": "A", "text": "符合"}, {"key": "B", "text": "不符合"}],
            answer_key=["A"],
            explanation="依据标注规范进行判断。",
            difficulty=0.5,
        )
        path_context.add(item)
        path_context.flush()
        path_context.add(
            AssessmentItemSkill(
                item_id=item.id,
                skill_code="annot.image",
                weight=1.0,
            )
        )
    path_context.commit()

    monkeypatch.setattr(learning_module, "LearningPathAgent", lambda: _agent())
    first = client.post(
        "/api/v1/students/stu_path/learning-paths/generate",
        json={"max_phases": 4},
    )
    assert first.status_code == 201, first.text
    old_path = first.json()["path"]
    retest = next(
        item
        for phase in old_path["phases"]
        for item in phase["items"]
        if item["item_type"] == "assessment"
    )

    started = client.post(
        f"/api/v1/students/stu_path/learning-path-items/{retest['id']}/retest",
        json={"item_count": 4},
    )
    assert started.status_code == 201, started.text
    assessment_id = started.json()["assessment_id"]
    assessment = client.get(f"/api/v1/assessments/{assessment_id}").json()

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        json={
            "responses": [
                {"item_id": item["id"], "response": ["B"]}
                for item in assessment["items"]
            ]
        },
    )
    assert submitted.status_code == 200, submitted.text
    update = submitted.json()["learning_path_update"]
    assert update["linked_item_id"] == retest["id"]
    assert update["archived_path_id"] == old_path["id"]
    assert update["recalculated"] is True
    assert update["new_path_id"] != old_path["id"]

    path_context.expire_all()
    assert (
        LearningPathService(path_context).latest_path(
            "stu_path", "ai_data_annotator"
        ).id
        == update["new_path_id"]
    )
    scored_activity = path_context.query(LearningPathActivity).filter_by(
        item_id=retest["id"], action="assessment_scored"
    ).one()
    assert scored_activity.ref_id == assessment_id
    old = path_context.get(learning_module.LearningPath, old_path["id"])
    assert old.status is PathStatus.ARCHIVED
