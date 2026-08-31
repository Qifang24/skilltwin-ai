"""岗位数据模型与导入校验测试。

重点：演示数据绝不能悄悄混进对外统计。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.core.enums import DataFlag, SkillCategory
from app.models.job_market import JobPosting, JobPostingSkill, SkillDemandSnapshot
from app.models.ontology import Job, Skill

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from import_postings import _validate, scrub_pii  # noqa: E402


@pytest.fixture
def seeded(db: Session) -> Session:
    db.add_all(
        [
            Job(id="ai_data_annotator", name="AI数据标注工程师"),
            Skill(
                skill_code="data.cleaning",
                name_zh="数据清洗",
                category=SkillCategory.DATA,
            ),
        ]
    )
    db.commit()
    return db


# ---------------------------------------------------------------- 脱敏
def test_scrub_removes_phone_number() -> None:
    text, changed = scrub_pii("联系人张经理 13812345678 速来")
    assert "13812345678" not in text
    assert changed is True


def test_scrub_removes_email_and_wechat() -> None:
    text, _ = scrub_pii("简历投 hr@example.com，微信：zhangsan_hr123")
    assert "hr@example.com" not in text
    assert "zhangsan_hr123" not in text


def test_scrub_leaves_clean_text_untouched() -> None:
    original = "岗位职责：负责图像数据标注，熟悉标注规范。"
    text, changed = scrub_pii(original)
    assert text == original
    assert changed is False


def test_scrub_keeps_non_phone_digits() -> None:
    """薪资、年份等数字不该被误伤。"""
    text, _ = scrub_pii("薪资 8000-12000 元，2025 年入职")
    assert "8000-12000" in text
    assert "2025" in text


# ---------------------------------------------------------------- 校验
_GOOD_TEXT = "岗位职责：负责图像、文本数据的标注工作，按标注规范完成作业并自检。任职要求：大专及以上学历，熟悉常用标注工具。"


def test_validate_accepts_good_entry() -> None:
    entry = {"id": "jp_1", "title": "数据标注工程师", "raw_text": _GOOD_TEXT, "data_flag": "REAL"}
    assert _validate(entry, 0, set()) == []


def test_validate_rejects_template_placeholder() -> None:
    """模板占位文字没换掉，是最容易犯的错，必须直接拦下。"""
    entry = {"id": "jp_1", "title": "x", "raw_text": "【把岗位描述原文完整粘贴到这里】"}
    problems = _validate(entry, 0, set())
    assert any("模板占位文字" in p for p in problems)


def test_validate_rejects_too_short_text() -> None:
    """只填关键词的话，技能证据无法从原文定位，等于断了证据链。"""
    problems = _validate({"id": "jp_1", "title": "x", "raw_text": "Python 标注"}, 0, set())
    assert any("疑似只填了关键词" in p for p in problems)


def test_validate_reports_missing_required_fields() -> None:
    problems = _validate({"title": "x"}, 0, set())
    assert any("`id`" in p for p in problems)
    assert any("`raw_text`" in p for p in problems)


def test_validate_detects_duplicate_id() -> None:
    entry = {"id": "jp_1", "title": "x", "raw_text": _GOOD_TEXT}
    problems = _validate(entry, 1, {"jp_1"})
    assert any("重复" in p for p in problems)


def test_validate_rejects_bad_data_flag() -> None:
    entry = {"id": "jp_1", "title": "x", "raw_text": _GOOD_TEXT, "data_flag": "真实"}
    assert any("data_flag" in p for p in _validate(entry, 0, set()))


def test_validate_reports_all_problems_at_once() -> None:
    """一次报全，别让人反复试错。"""
    problems = _validate({"raw_text": "短"}, 0, set())
    assert len(problems) >= 3


# ---------------------------------------------------------------- 模型
def test_posting_defaults_to_demo(seeded: Session) -> None:
    """默认必须是 DEMO —— 真实性要显式声明，不能靠默认蒙混。"""
    seeded.add(
        JobPosting(id="jp_1", job_id="ai_data_annotator", title="x", raw_text=_GOOD_TEXT)
    )
    seeded.commit()
    assert seeded.get(JobPosting, "jp_1").data_flag is DataFlag.DEMO


def test_posting_skill_requires_known_skill(seeded: Session) -> None:
    """技能外键必须由数据库强制，防止 join key 漂移。"""
    seeded.add(
        JobPosting(id="jp_1", job_id="ai_data_annotator", title="x", raw_text=_GOOD_TEXT)
    )
    seeded.commit()
    seeded.add(
        JobPostingSkill(
            posting_id="jp_1", skill_code="data.does_not_exist", evidence_span="…"
        )
    )
    with pytest.raises((IntegrityError, StatementError)):
        seeded.commit()
    seeded.rollback()


def test_same_skill_recorded_once_per_posting(seeded: Session) -> None:
    """同一条 JD 里同一技能只记一次，否则频次统计会被重复计数抬高。"""
    seeded.add(
        JobPosting(id="jp_1", job_id="ai_data_annotator", title="x", raw_text=_GOOD_TEXT)
    )
    seeded.commit()
    seeded.add(
        JobPostingSkill(posting_id="jp_1", skill_code="data.cleaning", evidence_span="a")
    )
    seeded.commit()
    seeded.add(
        JobPostingSkill(posting_id="jp_1", skill_code="data.cleaning", evidence_span="b")
    )
    with pytest.raises(IntegrityError):
        seeded.commit()
    seeded.rollback()


def test_snapshot_flags_demo_contamination(seeded: Session) -> None:
    """混入演示数据的统计必须能被识别出来，不得作为对外结论。"""
    clean = SkillDemandSnapshot(
        job_id="ai_data_annotator",
        skill_code="data.cleaning",
        posting_count=33,
        total_postings=40,
        frequency=0.825,
        real_posting_count=40,
        demo_posting_count=0,
        computed_at=datetime.now(timezone.utc),
    )
    dirty = SkillDemandSnapshot(
        job_id="ai_data_annotator",
        skill_code="data.cleaning",
        window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        posting_count=5,
        total_postings=10,
        frequency=0.5,
        real_posting_count=7,
        demo_posting_count=3,
    )
    seeded.add_all([clean, dirty])
    seeded.commit()

    assert clean.is_demo_contaminated is False
    assert dirty.is_demo_contaminated is True
