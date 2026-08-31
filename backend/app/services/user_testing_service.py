"""用户测试脚本、匿名记录与汇总报告。"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.db import utcnow
from app.core.enums import UserTestOutcome, UserTestRole, UserTestSessionStatus
from app.core.errors import NotFoundError, ValidationError
from app.models.user_testing import UserTestSession, UserTestTaskRecord
from app.schemas.user_testing import (
    CompleteUserTestSessionRequest,
    CreateUserTestSessionRequest,
    UpdateUserTestTaskRequest,
    UserTestReportRead,
    UserTestReportTaskRead,
    UserTestScriptRead,
    UserTestScriptTaskRead,
)


@dataclass(frozen=True)
class ScriptDefinition:
    id: str
    name: str
    participant_role: UserTestRole
    description: str
    tasks: tuple[tuple[str, str, str], ...]


_SCRIPTS = (
    ScriptDefinition(
        id="teacher_industry_to_training",
        name="教师端：产业需求到实训设计闭环",
        participant_role=UserTestRole.TEACHER,
        description="请以 AI 数据标注工程师为目标岗位，完成岗位需求、课程 Gap 与实训任务设计的核查。",
        tasks=(
            (
                "market_evidence",
                "查看岗位技能需求及其原文证据",
                "能够看到技能需求、样本质量提示，并下钻到公开 JD 原文片段。",
            ),
            (
                "curriculum_gap",
                "核查课程覆盖与岗位能力 Gap",
                "能够区分课程原文覆盖、未映射和岗位数据质量限制，不将资料缺失误判为培养缺口。",
            ),
            (
                "training_design",
                "从已审核能力图谱生成并查看实训任务",
                "能够得到结构化任务、评分量规、技能关联和来源提示。",
            ),
        ),
    ),
    ScriptDefinition(
        id="student_adaptive_learning",
        name="学生端：诊断到自适应学习闭环",
        participant_role=UserTestRole.STUDENT,
        description="请以 AI 数据标注工程师为目标岗位，完成诊断、查看能力差距、学习路径与 Tutor 辅导。",
        tasks=(
            (
                "diagnostic_profile",
                "完成诊断并查看能力画像",
                "能够查看能力雷达、分数区间和低证据提示，理解它不是绝对能力定论。",
            ),
            (
                "learning_path",
                "查看个性化学习路径",
                "能够理解每个学习阶段与能力 Gap、前置关系和实训任务的关联。",
            ),
            (
                "tutor_evidence",
                "在当前实训任务中向 AI Tutor 追问",
                "能够获得结合任务上下文的回答，并看到已核验、部分核验或证据不足状态与来源。",
            ),
        ),
    ),
)
_SCRIPT_BY_ID = {script.id: script for script in _SCRIPTS}


class UserTestingService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def scripts(self) -> list[UserTestScriptRead]:
        return [
            UserTestScriptRead(
                id=script.id,
                name=script.name,
                participant_role=script.participant_role,
                description=script.description,
                tasks=[
                    UserTestScriptTaskRead(code=code, title=title, expected_result=expected)
                    for code, title, expected in script.tasks
                ],
            )
            for script in _SCRIPTS
        ]

    def create_session(self, payload: CreateUserTestSessionRequest) -> UserTestSession:
        script = _SCRIPT_BY_ID.get(payload.script_id)
        if script is None:
            raise ValidationError("未知的用户测试脚本")
        if script.participant_role != payload.participant_role:
            raise ValidationError("测试脚本与参与者角色不匹配")
        if not payload.consent_confirmed:
            raise ValidationError("请先确认参与者知情同意后再记录测试")

        session = UserTestSession(
            id=f"ut_{uuid.uuid4().hex[:16]}",
            participant_alias=payload.participant_alias.strip(),
            participant_role=payload.participant_role,
            script_id=script.id,
            consent_confirmed=True,
        )
        self._db.add(session)
        self._db.flush()
        for index, (code, title, expected_result) in enumerate(script.tasks):
            self._db.add(
                UserTestTaskRecord(
                    id=f"utt_{uuid.uuid4().hex[:16]}",
                    session_id=session.id,
                    task_code=code,
                    title=title,
                    expected_result=expected_result,
                    order_index=index,
                )
            )
        self._db.flush()
        return session

    def get_session(self, session_id: str) -> UserTestSession:
        session = self._db.execute(
            select(UserTestSession)
            .options(selectinload(UserTestSession.tasks))
            .where(UserTestSession.id == session_id)
        ).scalar_one_or_none()
        if session is None:
            raise NotFoundError(f"未找到用户测试会话：{session_id}")
        return session

    def list_sessions(self) -> list[UserTestSession]:
        return self._db.execute(
            select(UserTestSession)
            .options(selectinload(UserTestSession.tasks))
            .order_by(UserTestSession.created_at.desc())
        ).scalars().all()

    def update_task(self, task_id: str, payload: UpdateUserTestTaskRequest) -> UserTestTaskRecord:
        task = self._db.get(UserTestTaskRecord, task_id)
        if task is None:
            raise NotFoundError(f"未找到用户测试任务：{task_id}")
        if task.session.status is UserTestSessionStatus.COMPLETED:
            raise ValidationError("已完成的用户测试会话不可再修改")
        task.actual_result = payload.actual_result.strip()
        task.outcome = payload.outcome
        task.accuracy = payload.accuracy
        task.ease_of_use = payload.ease_of_use
        task.feedback = payload.feedback.strip() if payload.feedback else None
        self._db.flush()
        return task

    def complete_session(
        self, session_id: str, payload: CompleteUserTestSessionRequest
    ) -> UserTestSession:
        session = self.get_session(session_id)
        if session.status is UserTestSessionStatus.COMPLETED:
            raise ValidationError("该用户测试会话已完成")
        incomplete = [
            task.title
            for task in session.tasks
            if task.actual_result is None
            or task.outcome is None
            or task.accuracy is None
            or task.ease_of_use is None
        ]
        if incomplete:
            raise ValidationError(
                "请先完成全部任务记录后再结束会话",
                detail={"incomplete_tasks": incomplete},
            )
        session.status = UserTestSessionStatus.COMPLETED
        session.overall_feedback = (
            payload.overall_feedback.strip() if payload.overall_feedback else None
        )
        session.completed_at = utcnow()
        self._db.flush()
        return session

    def delete_session(self, session_id: str) -> None:
        self._db.delete(self.get_session(session_id))
        self._db.flush()

    def report(self) -> UserTestReportRead:
        sessions = self.list_sessions()
        completed = [s for s in sessions if s.status is UserTestSessionStatus.COMPLETED]
        records = [task for session in completed for task in session.tasks]
        roles: dict[str, int] = defaultdict(int)
        for session in completed:
            roles[session.participant_role.value] += 1

        outcomes = [task.outcome for task in records if task.outcome is not None]
        accuracy = [task.accuracy for task in records if task.accuracy is not None]
        ease = [task.ease_of_use for task in records if task.ease_of_use is not None]
        grouped: dict[str, list[UserTestTaskRecord]] = defaultdict(list)
        for record in records:
            grouped[record.task_code].append(record)

        task_rows = []
        for code, items in sorted(grouped.items()):
            task_rows.append(
                UserTestReportTaskRead(
                    task_code=code,
                    title=items[0].title,
                    response_count=len(items),
                    completion_rate=round(
                        sum(item.outcome is UserTestOutcome.COMPLETED for item in items)
                        / len(items),
                        3,
                    ),
                    average_accuracy=round(
                        sum(item.accuracy or 0 for item in items) / len(items), 2
                    ),
                    average_ease_of_use=round(
                        sum(item.ease_of_use or 0 for item in items) / len(items), 2
                    ),
                    feedback_samples=[item.feedback for item in items if item.feedback][:5],
                )
            )

        warnings: list[str] = []
        if len(completed) < 2:
            warnings.append("已完成样本少于 2 名，当前汇总仅用于试运行观察，不可作结论性判断")
        if not completed:
            warnings.append("尚无已完成的真实用户测试记录，系统不会生成测试结论")
        return UserTestReportRead(
            completed_sessions=len(completed),
            draft_sessions=len(sessions) - len(completed),
            participant_roles=dict(roles),
            task_records=len(records),
            overall_completion_rate=(
                round(sum(item is UserTestOutcome.COMPLETED for item in outcomes) / len(outcomes), 3)
                if outcomes
                else None
            ),
            average_accuracy=round(sum(accuracy) / len(accuracy), 2) if accuracy else None,
            average_ease_of_use=round(sum(ease) / len(ease), 2) if ease else None,
            tasks=task_rows,
            overall_feedback_samples=[
                session.overall_feedback
                for session in completed
                if session.overall_feedback
            ][:10],
            warnings=warnings,
            reasoning_summary=(
                "所有指标仅由已完成会话中的任务记录直接汇总；"
                "草稿会话和缺失评分不会被填补或推断。"
            ),
        )
