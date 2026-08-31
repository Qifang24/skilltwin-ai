"""Phase 15 用户测试：匿名记录、真实汇总与删除。"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.enums import UserTestOutcome, UserTestRole, UserTestSessionStatus
from app.core.errors import ValidationError
from app.schemas.user_testing import (
    CompleteUserTestSessionRequest,
    CreateUserTestSessionRequest,
    UpdateUserTestTaskRequest,
)
from app.services.user_testing_service import UserTestingService


def _create_teacher_session(service: UserTestingService):
    return service.create_session(
        CreateUserTestSessionRequest(
            participant_alias="教师测试者01",
            participant_role=UserTestRole.TEACHER,
            script_id="teacher_industry_to_training",
            consent_confirmed=True,
        )
    )


def _record_all(service: UserTestingService, session_id: str) -> None:
    session = service.get_session(session_id)
    for task in session.tasks:
        service.update_task(
            task.id,
            UpdateUserTestTaskRequest(
                actual_result="测试者成功完成任务，并能解释页面中的证据与提示。",
                outcome=UserTestOutcome.COMPLETED,
                accuracy=5,
                ease_of_use=4,
                feedback="任务路径清晰。",
            ),
        )


def test_session_uses_anonymous_alias_and_script_tasks(db: Session) -> None:
    service = UserTestingService(db)
    session = _create_teacher_session(service)
    db.commit()

    loaded = service.get_session(session.id)
    assert loaded.participant_alias == "教师测试者01"
    assert loaded.status is UserTestSessionStatus.DRAFT
    assert len(loaded.tasks) == 3
    assert all(task.expected_result for task in loaded.tasks)


def test_consent_and_role_mismatch_are_rejected(db: Session) -> None:
    service = UserTestingService(db)
    with pytest.raises(ValidationError, match="知情同意"):
        service.create_session(
            CreateUserTestSessionRequest(
                participant_alias="学生01",
                participant_role=UserTestRole.STUDENT,
                script_id="student_adaptive_learning",
                consent_confirmed=False,
            )
        )
    with pytest.raises(ValidationError, match="角色不匹配"):
        service.create_session(
            CreateUserTestSessionRequest(
                participant_alias="学生01",
                participant_role=UserTestRole.STUDENT,
                script_id="teacher_industry_to_training",
                consent_confirmed=True,
            )
        )


def test_report_counts_only_completed_sessions(db: Session) -> None:
    service = UserTestingService(db)
    completed = _create_teacher_session(service)
    draft = _create_teacher_session(service)
    _record_all(service, completed.id)
    service.complete_session(
        completed.id,
        CompleteUserTestSessionRequest(overall_feedback="总体流程可理解。"),
    )
    db.commit()

    report = service.report()
    assert report.completed_sessions == 1
    assert report.draft_sessions == 1
    assert report.task_records == 3
    assert report.overall_completion_rate == 1.0
    assert report.average_accuracy == 5.0
    assert report.average_ease_of_use == 4.0
    assert report.tasks[0].response_count == 1
    assert report.warnings  # 少量样本不得伪装成结论
    assert draft.id != completed.id


def test_session_cannot_complete_without_all_observations_and_can_be_deleted(db: Session) -> None:
    service = UserTestingService(db)
    session = _create_teacher_session(service)
    with pytest.raises(ValidationError, match="完成全部任务记录"):
        service.complete_session(session.id, CompleteUserTestSessionRequest())

    _record_all(service, session.id)
    service.complete_session(session.id, CompleteUserTestSessionRequest())
    with pytest.raises(ValidationError, match="不可再修改"):
        service.update_task(
            session.tasks[0].id,
            UpdateUserTestTaskRequest(
                actual_result="修改",
                outcome=UserTestOutcome.COMPLETED,
                accuracy=5,
                ease_of_use=5,
            ),
        )
    service.delete_session(session.id)
    db.commit()
    assert service.list_sessions() == []


def test_api_returns_scripts_and_report(client) -> None:  # noqa: ANN001
    scripts = client.get("/api/v1/user-testing/scripts")
    report = client.get("/api/v1/user-testing/report")
    assert scripts.status_code == 200 and len(scripts.json()) == 2
    assert report.status_code == 200
    assert report.json()["completed_sessions"] == 0
    assert "不会生成测试结论" in " ".join(report.json()["warnings"])
