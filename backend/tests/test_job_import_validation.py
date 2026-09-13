"""Focused validation and encoding coverage for staged job imports."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.core.enums import Provenance, SkillCategory, SkillStatus
from app.models.job_market import JobPostingSkill, JobSkillCandidate
from app.models.ontology import Skill


def test_gb18030_csv_auto_maps_position_name_and_stays_staged(client, db) -> None:
    csv_text = (
        "position_name,company,jd,city,published_at,source,url\n"
        "数据标注员,示例企业,负责图像标注与数据清洗,南京,2026-09-01,校园招聘,https://example.test/jobs/gb\n"
    )
    response = client.post(
        "/api/v1/job-imports",
        data={"job_id": "annotator", "job_name": "数据标注员"},
        files={"file": ("jobs.csv", csv_text.encode("gb18030"), "text/csv")},
    )

    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["field_mapping"]["title"] == "position_name"
    assert batch["field_mapping"]["raw_text"] == "jd"
    assert batch["rows"][0]["status"] == "valid"
    # Creating and previewing a batch must never create formal postings.
    assert client.get("/api/v1/job-market/annotator/postings").json() == []


def test_preview_reports_required_date_city_source_and_url_errors(client) -> None:
    payload = [
        {"title": "", "raw_text": "有效但岗位名缺失的正文", "source_name": "招聘站"},
        {"title": "日期错误", "raw_text": "日期格式异常且正文唯一", "source_name": "招聘站", "posted_at": "昨天"},
        {"title": "城市错误", "raw_text": "城市字段含联系方式且正文唯一", "source_name": "招聘站", "city": "联系 hr@example.test"},
        {"title": "来源缺失", "raw_text": "来源字段为空且正文唯一", "source_name": ""},
        {"title": "链接错误", "raw_text": "来源链接格式错误且正文唯一", "source_name": "招聘站", "source_url": "ftp://example.test/job"},
        {"title": "JD 缺失", "raw_text": "", "source_name": "招聘站"},
    ]
    response = client.post(
        "/api/v1/job-imports",
        data={"job_id": "invalid_rows", "job_name": "无效记录检查"},
        files={"file": ("invalid.json", json.dumps(payload, ensure_ascii=False).encode(), "application/json")},
    )

    assert response.status_code == 201, response.text
    rows = response.json()["rows"]
    assert all(row["status"] == "invalid" for row in rows)
    errors = ["；".join(row["errors"]) for row in rows]
    assert "title 为必填字段" in errors[0]
    assert "日期格式错误" in errors[1]
    assert "城市字段疑似包含链接或联系方式" in errors[2]
    assert "source_name 为必填字段" in errors[3]
    assert "source_url 必须是有效的 HTTP(S) 地址" in errors[4]
    assert "raw_text 为必填字段" in errors[5]
    rejected = client.post(f"/api/v1/job-imports/{response.json()['id']}/confirm")
    assert rejected.status_code == 422
    assert "没有可导入记录" in rejected.json()["error"]["message"]
    assert client.get("/api/v1/job-market/invalid_rows/postings").json() == []


def test_manual_mapping_can_override_guessed_columns(client) -> None:
    payload = [{"name": "NLP 标注", "body": "负责文本分类与实体标注", "origin": "校招"}]
    created = client.post(
        "/api/v1/job-imports",
        data={"job_id": "nlp_annotator", "job_name": "NLP 标注"},
        files={"file": ("custom.json", json.dumps(payload, ensure_ascii=False).encode(), "application/json")},
    )
    assert created.status_code == 201, created.text
    batch_id = created.json()["id"]
    assert created.json()["rows"][0]["status"] == "invalid"

    mapped = client.patch(
        f"/api/v1/job-imports/{batch_id}/mapping",
        json={"mapping": {"title": "name", "raw_text": "body", "source_name": "origin"}},
    )
    assert mapped.status_code == 200, mapped.text
    row = mapped.json()["rows"][0]
    assert row["status"] == "valid"
    assert row["normalized_data"]["title"] == "NLP 标注"
    assert row["normalized_data"]["raw_text"] == "负责文本分类与实体标注"


def test_empty_and_unsupported_files_have_actionable_errors(client) -> None:
    common = {"job_id": "file_errors", "job_name": "文件错误"}
    empty = client.post(
        "/api/v1/job-imports",
        data=common,
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert empty.status_code == 422
    assert "上传文件为空" in empty.json()["error"]["message"]

    unsupported = client.post(
        "/api/v1/job-imports",
        data=common,
        files={"file": ("jobs.xlsx", b"not-an-xlsx", "application/octet-stream")},
    )
    assert unsupported.status_code == 422
    assert "仅支持 CSV 和 JSON" in unsupported.json()["error"]["message"]


def test_json_skill_array_links_known_skill_and_queues_unknown_candidate(client, db) -> None:
    db.add(Skill(
        skill_code="prog.python", name_zh="Python", name_en="Python",
        category=SkillCategory.PROGRAMMING, aliases=[], status=SkillStatus.ACTIVE,
        provenance=Provenance.HUMAN_AUTHORED,
    ))
    db.commit()
    payload = [{
        "title": "数据工程师", "raw_text": "负责数据处理、清洗和质量检查工作。",
        "source_name": "校园招聘", "skills": ["prog.python", "新工具能力"],
    }]
    created = client.post(
        "/api/v1/job-imports",
        data={"job_id": "json_skills", "job_name": "数据工程师"},
        files={"file": ("skills.json", json.dumps(payload, ensure_ascii=False).encode(), "application/json")},
    )
    assert created.status_code == 201, created.text
    confirmed = client.post(f"/api/v1/job-imports/{created.json()['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    posting_id = confirmed.json()["rows"][0]["posting_id"]
    assert db.execute(select(JobPostingSkill).where(
        JobPostingSkill.posting_id == posting_id,
        JobPostingSkill.skill_code == "prog.python",
    )).scalar_one()
    candidate = db.execute(select(JobSkillCandidate).where(
        JobSkillCandidate.posting_id == posting_id,
    )).scalar_one()
    assert candidate.candidate_name == "新工具能力"
