"""测评流程与能力画像测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import (
    AssessmentStatus,
    AssessmentType,
    ItemType,
    ProfileSource,
    SkillCategory,
)
from app.core.errors import ConflictError, ValidationError
from app.models.ontology import Job, Skill
from app.models.student import (
    Assessment,
    AssessmentItem,
    AssessmentItemSkill,
    AssessmentResponse,
    SkillProfile,
    SkillProfileEntry,
    Student,
)
from app.services.assessment_service import AssessmentService, grade_objective


@pytest.fixture
def bank(db: Session) -> Session:
    db.add(Job(id="ai_data_annotator", name="AI数据标注工程师"))
    db.add_all([
        Skill(skill_code="annot.image", name_zh="视觉数据标注", category=SkillCategory.ANNOTATION),
        Skill(skill_code="quality.audit", name_zh="标注数据审核", category=SkillCategory.QUALITY),
    ])
    db.add(Student(id="stu_1", display_name="学生A", target_job_id="ai_data_annotator"))
    db.commit()

    for index in range(6):
        code = "annot.image" if index % 2 == 0 else "quality.audit"
        item = AssessmentItem(
            id=f"item_{index}",
            job_id="ai_data_annotator",
            stem=f"第{index}题：以下哪种标注方式符合规范？",
            item_type=ItemType.SINGLE,
            options=[{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}],
            answer_key=["A"],
            explanation="解析",
            difficulty=0.5,
        )
        db.add(item)
        db.flush()
        db.add(AssessmentItemSkill(item_id=item.id, skill_code=code, weight=1.0))
    db.commit()
    return db


# ---------------------------------------------------------------- 判分
def test_exact_match_scores_one() -> None:
    assert grade_objective(["A"], ["A"]) == 1.0


def test_multi_choice_needs_all_correct() -> None:
    """多选不给部分分：部分分会让「一题一证据」的估计假设失效。"""
    assert grade_objective(["A", "C"], ["A"]) == 0.0
    assert grade_objective(["A", "C"], ["C", "A"]) == 1.0  # 顺序无关


def test_wrong_answer_scores_zero() -> None:
    assert grade_objective(["A"], ["B"]) == 0.0


def test_empty_response_scores_zero() -> None:
    assert grade_objective(["A"], []) == 0.0


# ---------------------------------------------------------------- 组卷
def test_start_requires_item_bank(db: Session) -> None:
    db.add(Job(id="empty_job", name="空岗位"))
    db.add(Student(id="s", display_name="学生"))
    db.commit()
    with pytest.raises(ValidationError, match="题库为空"):
        AssessmentService(db).start(
            student=db.get(Student, "s"), job_id="empty_job", item_count=4
        )


def test_start_covers_all_skills(bank: Session) -> None:
    """组卷必须覆盖各技能，随机抽题会让某些技能一题都没有。"""
    service = AssessmentService(bank)
    assessment = service.start(
        student=bank.get(Student, "stu_1"), job_id="ai_data_annotator", item_count=4
    ).assessment
    bank.commit()

    codes = set()
    for record in assessment.responses:
        item = bank.get(AssessmentItem, record.item_id)
        codes.update(link.skill_code for link in item.skills)
    assert codes == {"annot.image", "quality.audit"}


def test_start_locks_paper(bank: Session) -> None:
    """开考即锁定卷面，之后题库变动不影响这份卷子。"""
    service = AssessmentService(bank)
    assessment = service.start(
        student=bank.get(Student, "stu_1"), job_id="ai_data_annotator", item_count=4
    ).assessment
    bank.commit()
    assert len(assessment.responses) == 4
    assert assessment.status is AssessmentStatus.IN_PROGRESS


# ---------------------------------------------------------------- 提交
def _submit_all(db: Session, correct: bool):
    service = AssessmentService(db)
    assessment = service.start(
        student=db.get(Student, "stu_1"), job_id="ai_data_annotator", item_count=6
    ).assessment
    db.commit()
    answers = {r.item_id: (["A"] if correct else ["B"]) for r in assessment.responses}
    result = service.submit(assessment.id, answers)
    db.commit()
    return service, assessment, result


def test_submit_produces_profile_with_confidence(bank: Session) -> None:
    _, _, result = _submit_all(bank, correct=True)

    assert result.correct_count == 6
    assert len(result.profile.entries) == 2
    for entry in result.profile.entries:
        assert entry.score_low < entry.score < entry.score_high or entry.score_high == 100
        assert 0 <= entry.confidence <= 1
        assert entry.evidence_count == 3


def test_all_correct_does_not_yield_100(bank: Session) -> None:
    """全对也不该是满分 —— 3 题的样本撑不起「能力 100」这个结论。"""
    _, _, result = _submit_all(bank, correct=True)
    for entry in result.profile.entries:
        assert entry.score < 100, f"{entry.skill_code} 给了满分，属假精度"


def test_thin_evidence_is_flagged_in_notes(bank: Session) -> None:
    """证据不足必须如实说明，不能让用户以为这份画像很准。"""
    _, _, result = _submit_all(bank, correct=True)
    assert any("置信度低于" in n for n in result.notes)


def test_all_wrong_is_not_certainly_zero(bank: Session) -> None:
    _, _, result = _submit_all(bank, correct=False)
    for entry in result.profile.entries:
        assert entry.score_high > 0, "全错也不能断言能力上界为 0"


def test_cannot_submit_twice(bank: Session) -> None:
    service, assessment, _ = _submit_all(bank, correct=True)
    with pytest.raises(ConflictError, match="已判分"):
        service.submit(assessment.id, {})


def test_latest_profile_returns_newest(bank: Session) -> None:
    service, _, first = _submit_all(bank, correct=False)
    _, _, second = _submit_all(bank, correct=True)
    latest = service.latest_profile("stu_1")
    assert latest is not None
    assert latest.id == second.profile.id


def test_partial_retest_preserves_unmeasured_skills(bank: Session) -> None:
    """局部复测只能覆盖命中的技能，不能让其他能力从最新画像中消失。"""
    service, _, initial = _submit_all(bank, correct=True)
    before = {entry.skill_code: entry for entry in initial.profile.entries}

    retest = Assessment(
        id="asmt_partial_retest",
        student_id="stu_1",
        job_id="ai_data_annotator",
        type=AssessmentType.RETEST,
        status=AssessmentStatus.IN_PROGRESS,
        started_at=utcnow(),
    )
    bank.add(retest)
    bank.flush()
    bank.add(
        AssessmentResponse(assessment_id=retest.id, item_id="item_0")
    )  # item_0 只考 annot.image
    bank.commit()

    result = service.submit(retest.id, {"item_0": ["B"]})
    bank.commit()
    after = {entry.skill_code: entry for entry in result.profile.entries}

    assert result.profile.source is ProfileSource.MERGED
    assert set(after) == {"annot.image", "quality.audit"}
    assert result.updated_skill_codes == ["annot.image"]
    assert result.inherited_skill_codes == ["quality.audit"]
    assert after["annot.image"].score != before["annot.image"].score
    assert after["quality.audit"].score == before["quality.audit"].score
    assert (
        after["quality.audit"].evidence_count
        == before["quality.audit"].evidence_count
    )
    assert any("沿用上一份同岗位画像" in note for note in result.notes)


def test_merge_never_inherits_from_another_job(bank: Session) -> None:
    """学生切换目标岗位时，两个岗位的能力向量必须严格隔离。"""
    bank.add(Job(id="python_developer", name="Python开发工程师"))
    bank.add(
        Skill(
            skill_code="prog.python",
            name_zh="Python编程",
            category=SkillCategory.PROGRAMMING,
        )
    )
    other = SkillProfile(
        id="prof_other_job",
        student_id="stu_1",
        job_id="python_developer",
        computed_at=utcnow(),
    )
    bank.add(other)
    bank.flush()
    bank.add(
        SkillProfileEntry(
            profile_id=other.id,
            skill_code="prog.python",
            score=88,
            score_low=75,
            score_high=95,
            confidence=0.8,
            evidence_count=12,
            method="wilson",
        )
    )
    bank.commit()

    _, _, result = _submit_all(bank, correct=True)
    codes = {entry.skill_code for entry in result.profile.entries}
    assert "prog.python" not in codes
    assert AssessmentService(bank).latest_profile(
        "stu_1", "python_developer"
    ).id == "prof_other_job"


def test_first_diagnostic_is_not_marked_as_merged(bank: Session) -> None:
    _, _, result = _submit_all(bank, correct=True)
    assert result.profile.source is ProfileSource.DIAGNOSTIC
    assert result.inherited_skill_codes == []


def test_profile_api_filters_snapshots_by_job(bank: Session, client) -> None:
    """查询画像时应默认目标岗位，也允许显式查看其他岗位，不能取全局最新。"""
    _, _, first = _submit_all(bank, correct=True)
    bank.add(Job(id="python_developer", name="Python开发工程师"))
    bank.add(
        Skill(
            skill_code="prog.python",
            name_zh="Python编程",
            category=SkillCategory.PROGRAMMING,
        )
    )
    other = SkillProfile(
        id="prof_api_other_job",
        student_id="stu_1",
        job_id="python_developer",
        computed_at=utcnow(),
    )
    bank.add(other)
    bank.flush()
    bank.add(
        SkillProfileEntry(
            profile_id=other.id,
            skill_code="prog.python",
            score=88,
            score_low=75,
            score_high=95,
            confidence=0.8,
            evidence_count=12,
            method="wilson",
        )
    )
    bank.commit()

    default_response = client.get("/api/v1/students/stu_1/skill-profile")
    assert default_response.status_code == 200
    assert default_response.json()["id"] == first.profile.id

    other_response = client.get(
        "/api/v1/students/stu_1/skill-profile",
        params={"job_id": "python_developer"},
    )
    assert other_response.status_code == 200
    assert other_response.json()["id"] == "prof_api_other_job"
    assert other_response.json()["entries"][0]["skill_code"] == "prog.python"


def test_partial_retest_api_exposes_updated_and_inherited_skills(
    bank: Session, client
) -> None:
    _submit_all(bank, correct=True)
    retest = Assessment(
        id="asmt_api_partial",
        student_id="stu_1",
        job_id="ai_data_annotator",
        type=AssessmentType.RETEST,
        status=AssessmentStatus.IN_PROGRESS,
        started_at=utcnow(),
    )
    bank.add(retest)
    bank.flush()
    bank.add(AssessmentResponse(assessment_id=retest.id, item_id="item_0"))
    bank.commit()

    response = client.post(
        "/api/v1/assessments/asmt_api_partial/submit",
        json={"responses": [{"item_id": "item_0", "response": ["B"]}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated_skill_codes"] == ["annot.image"]
    assert body["inherited_skill_codes"] == ["quality.audit"]
    assert body["profile"]["source"] == "merged"
    assert {entry["skill_code"] for entry in body["profile"]["entries"]} == {
        "annot.image",
        "quality.audit",
    }


def test_deleting_student_removes_everything(bank: Session) -> None:
    """合规要求：学生数据必须可彻底删除。"""
    _submit_all(bank, correct=True)
    bank.delete(bank.get(Student, "stu_1"))
    bank.commit()

    assert bank.query(SkillProfile).count() == 0


def test_start_warns_when_items_too_few_for_skills(bank: Session) -> None:
    """题量相对技能数偏少时，必须在**开考前**提示。

    等交完卷才说「14 项全部不可信」，学生已经白做了一遍。
    """
    started = AssessmentService(bank).start(
        student=bank.get(Student, "stu_1"), job_id="ai_data_annotator", item_count=2
    )
    bank.commit()
    assert any("不宜作为精确评价" in n for n in started.notes)


def test_start_no_warning_when_evidence_sufficient(bank: Session) -> None:
    started = AssessmentService(bank).start(
        student=bank.get(Student, "stu_1"), job_id="ai_data_annotator", item_count=6
    )
    bank.commit()
    assert started.notes == []
