"""Phase 10：JD 原文技能抽取、需求快照、趋势与 API 测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.enums import DataFlag, SkillCategory
from app.models.job_market import JobPosting, JobPostingSkill, SkillDemandSnapshot
from app.models.ontology import Job, Skill
from app.services.job_market_service import JobMarketService


@pytest.fixture
def market_context(db: Session) -> Session:
    db.add(Job(id="ai_data_annotator", name="AI数据标注工程师"))
    db.add_all(
        [
            Skill(
                skill_code="prog.python",
                name_zh="Python 编程",
                name_en="Python",
                aliases=["Python语言"],
                category=SkillCategory.TOOL,
            ),
            Skill(
                skill_code="tool.cvat",
                name_zh="CVAT",
                aliases=["CVAT 标注工具"],
                category=SkillCategory.TOOL,
            ),
            Skill(
                skill_code="data.cleaning",
                name_zh="数据清洗",
                category=SkillCategory.DATA,
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            JobPosting(
                id="jp_market_1",
                job_id="ai_data_annotator",
                title="数据标注工程师 A",
                raw_text=(
                    "岗位职责：使用 Python 完成数据清洗，并通过 CVAT 进行图像标注和质量检查。"
                    "任职要求：沟通认真，能遵守数据规范。"
                ),
                posted_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
                data_flag=DataFlag.REAL,
                source_name="公开招聘平台",
                source_url="https://example.com/jp_market_1",
            ),
            JobPosting(
                id="jp_market_2",
                job_id="ai_data_annotator",
                title="AI 训练师 B",
                raw_text=(
                    "岗位职责：负责 Python 数据处理和数据清洗，维护训练数据集。"
                    "任职要求：有数据标注项目经验。"
                ),
                posted_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
                data_flag=DataFlag.REAL,
            ),
            JobPosting(
                id="jp_market_3",
                job_id="ai_data_annotator",
                title="数据标注工程师（DEMO）",
                raw_text=(
                    "岗位职责：使用 CVAT 完成目标检测标注和数据清洗。"
                    "任职要求：熟悉标注质量复核。"
                ),
                posted_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                data_flag=DataFlag.DEMO,
            ),
        ]
    )
    db.commit()
    return db


def test_analysis_creates_evidence_backed_ranking_and_monthly_trends(
    market_context: Session,
) -> None:
    result = JobMarketService(market_context).analyze("ai_data_annotator")
    market_context.commit()

    assert result.extracted_skill_links == 7
    # 存在真实样本时，DEMO 只用于管线回归，不进入快照统计。
    assert result.snapshots_written == 8  # 全量 3 项 + 7 月 3 项 + 8 月 2 项

    dashboard = JobMarketService(market_context).dashboard("ai_data_annotator")
    assert dashboard.data_quality.total_postings == 3
    assert dashboard.data_quality.real_postings == 2
    assert dashboard.data_quality.demo_postings == 1
    assert any("DEMO" in warning for warning in dashboard.data_quality.warnings)

    python = next(item for item in dashboard.ranking if item.skill_code == "prog.python")
    assert python.posting_count == 2
    assert python.total_postings == 2
    assert python.frequency == pytest.approx(1.0)
    assert python.is_demo_contaminated is False
    assert python.evidence
    assert all(item.data_flag is DataFlag.REAL for item in python.evidence)
    posting = market_context.get(JobPosting, python.evidence[0].posting_id)
    assert python.evidence[0].evidence_span in posting.raw_text

    python_trend = next(item for item in dashboard.trends if item.skill_code == "prog.python")
    assert len(python_trend.points) == 2
    assert [point.total_postings for point in python_trend.points] == [1, 1]


def test_reanalysis_replaces_old_extraction_and_snapshot_rows(
    market_context: Session,
) -> None:
    service = JobMarketService(market_context)
    service.analyze("ai_data_annotator")
    market_context.commit()

    service.analyze("ai_data_annotator")
    market_context.commit()

    assert market_context.query(JobPostingSkill).count() == 7
    assert market_context.query(SkillDemandSnapshot).count() == 8


def test_job_market_api_returns_empty_but_explainable_dashboard(
    db: Session, client
) -> None:
    db.add(Job(id="empty_job", name="空岗位"))
    db.commit()

    response = client.get("/api/v1/job-market/empty_job/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["ranking"] == []
    assert body["data_quality"]["total_postings"] == 0
    assert "没有已导入岗位样本" in body["data_quality"]["warnings"][0]


def test_job_market_analyze_api(market_context: Session, client) -> None:
    response = client.post("/api/v1/job-market/ai_data_annotator/analyze")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["extracted_skill_links"] == 7
    assert body["dashboard"]["ranking"][0]["evidence"]


def test_import_job_postings_validates_source_scrubs_pii_and_rebuilds_dashboard(
    market_context: Session, client, db: Session
) -> None:
    response = client.post(
        "/api/v1/job-market/import",
        json={
            "job_id": "ai_data_annotator",
            "job_name": "AI 数据标注工程师",
            "postings": [
                {
                    "id": "imported_public_jd_1",
                    "title": "数据标注工程师",
                    "raw_text": "岗位职责：使用 Python 完成数据清洗与图像标注，负责质量检查。联系 13800138000，工作认真细致并遵守数据规范。",
                    "source_name": "公开招聘平台",
                    "source_url": "https://example.com/imported_public_jd_1",
                    "posted_at": "2026-09-10T00:00:00+08:00",
                    "data_flag": "REAL",
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["pii_scrubbed"] == 1
    assert body["dashboard"]["data_quality"]["real_postings"] == 3

    db.expire_all()
    posting = db.get(JobPosting, "imported_public_jd_1")
    assert posting is not None
    assert "13800138000" not in posting.raw_text
    assert "[手机号已脱敏]" in posting.raw_text


def test_import_job_postings_requires_real_posting_date(client) -> None:
    response = client.post(
        "/api/v1/job-market/import",
        json={
            "postings": [
                {
                    "id": "missing-date-jd",
                    "title": "数据标注工程师",
                    "raw_text": "岗位职责：负责图像数据标注、质量检查和标注结果复核，确保训练数据符合业务标准，并持续记录问题反馈和处理过程。",
                    "source_name": "公开招聘平台",
                    "source_url": "https://example.com/missing-date-jd",
                    "data_flag": "REAL",
                }
            ]
        },
    )
    assert response.status_code == 422
    assert "发布日期" in response.text
