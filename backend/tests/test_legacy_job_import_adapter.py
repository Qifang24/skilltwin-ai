"""Compatibility coverage for POST /job-market/import using staged services."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.enums import SkillCategory
from app.models.job_market import (
    JobImportBatch,
    JobPosting,
    JobPostingSkill,
    JobSkillCandidate,
    SkillDemandSnapshot,
)
from app.models.ontology import Job, Skill
from app.services.job_market_service import JobMarketService


def _payload(*, posting_id: str, title: str, text: str) -> dict:
    return {
        "job_id": "legacy_data_job",
        "job_name": "旧接口数据岗位",
        "postings": [{
            "id": posting_id,
            "title": title,
            "raw_text": text,
            "source_name": "公开招聘站",
            "source_url": f"https://example.test/jobs/{posting_id}",
            "posted_at": "2026-09-12T00:00:00+08:00",
            "data_flag": "REAL",
            "skill_codes": ["prog.python", "vendor.unknown_tool"],
        }],
    }


def test_legacy_api_preserves_ids_updates_duplicates_and_declared_skills(client, db) -> None:
    db.add(Skill(skill_code="prog.python", name_zh="Python", name_en="Python", category=SkillCategory.PROGRAMMING))
    db.commit()
    first_text = "负责数据处理、任务调度和结果交付，能够独立排查业务数据问题并形成完整处理记录，同时维护数据规范和交付质量台账。"
    created = client.post(
        "/api/v1/job-market/import",
        json=_payload(posting_id="legacy-post-1", title="数据处理工程师", text=first_text),
    )
    assert created.status_code == 200, created.text
    assert created.json()["created"] == 1
    assert created.json()["updated"] == 0

    db.expire_all()
    posting = db.get(JobPosting, "legacy-post-1")
    assert posting is not None
    assert posting.source_record_id == "legacy-post-1"
    assert posting.extra["declared_skills"] == "prog.python,vendor.unknown_tool"
    link = db.execute(select(JobPostingSkill).where(JobPostingSkill.posting_id == posting.id, JobPostingSkill.skill_code == "prog.python")).scalar_one()
    assert "prog.python" in link.evidence_span
    assert db.execute(select(JobSkillCandidate).where(JobSkillCandidate.posting_id == posting.id, JobSkillCandidate.candidate_name == "vendor.unknown_tool")).scalar_one()
    assert db.scalar(select(func.count()).select_from(SkillDemandSnapshot)) > 0

    updated_text = "负责数据平台治理、任务编排和质量复核，持续提交可追踪的数据处理报告并推动问题闭环，同时维护团队的数据规范和审核台账。"
    updated = client.post(
        "/api/v1/job-market/import",
        json=_payload(posting_id="legacy-post-1", title="高级数据处理工程师", text=updated_text),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["created"] == 0
    assert updated.json()["updated"] == 1
    db.expire_all()
    assert db.get(JobPosting, "legacy-post-1").title == "高级数据处理工程师"
    assert db.scalar(select(func.count()).select_from(JobPosting)) == 1

    duplicate = client.post(
        "/api/v1/job-market/import",
        json=_payload(posting_id="legacy-post-2", title="重复抓取", text=updated_text),
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["created"] == 0
    assert duplicate.json()["updated"] == 0
    assert duplicate.json()["skipped_duplicates"] == 1
    assert db.scalar(select(func.count()).select_from(JobPosting)) == 1
    assert db.scalar(select(func.count()).select_from(JobImportBatch)) == 3


def test_legacy_api_rolls_back_batch_job_and_posting_when_analysis_fails(
    client, db, monkeypatch
) -> None:
    db.add(Skill(skill_code="prog.python", name_zh="Python", name_en="Python", category=SkillCategory.PROGRAMMING))
    db.commit()

    def fail_analysis(self, job_id):  # noqa: ANN001, ARG001
        raise RuntimeError("forced analysis failure")

    monkeypatch.setattr(JobMarketService, "analyze", fail_analysis)
    with pytest.raises(RuntimeError, match="forced analysis failure"):
        client.post(
            "/api/v1/job-market/import",
            json=_payload(
                posting_id="rollback-post",
                title="应回滚岗位",
                text="负责数据清洗、数据审核和交付记录维护，能够完成业务问题定位与处理结果复盘，同时持续维护质量规范和完整操作台账。",
            ),
        )
    db.expire_all()
    assert db.get(JobPosting, "rollback-post") is None
    assert db.get(Job, "legacy_data_job") is None
    assert db.scalar(select(func.count()).select_from(JobImportBatch)) == 0
    assert db.scalar(select(func.count()).select_from(SkillDemandSnapshot)) == 0
