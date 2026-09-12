"""岗位技能需求与趋势接口（Phase 10）。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.enums import DataFlag
from app.core.errors import ValidationError
from app.models.job_market import JobPosting
from app.models.ontology import Job
from app.schemas.job_market import (
    JobMarketAnalyzeResponse,
    JobMarketDashboardRead,
    JobPostingImportRequest,
    JobPostingImportResponse,
)
from app.services.job_market_service import JobMarketService

router = APIRouter(prefix="/job-market", tags=["job-market"])

_PII_PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "[手机号已脱敏]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[邮箱已脱敏]"),
    (re.compile(r"(微信|weixin|wechat|VX|vx)[:：\s]*[A-Za-z0-9_-]{5,}"), "[微信号已脱敏]"),
]


def _scrub_pii(text: str) -> tuple[str, bool]:
    scrubbed = text
    for pattern, replacement in _PII_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed, scrubbed != text


@router.post("/import", response_model=JobPostingImportResponse, summary="导入并校验公开岗位 JD")
def import_job_postings(
    payload: JobPostingImportRequest, db: Session = Depends(get_db)
) -> JobPostingImportResponse:
    """管理端导入：保留原文、来源和日期，自动脱敏并重建可回查的技能统计。"""
    ids: set[str] = set()
    raw_texts: set[str] = set()
    for index, item in enumerate(payload.postings, start=1):
        if item.id in ids:
            raise ValidationError(f"第 {index} 条岗位记录的 ID 重复：{item.id}")
        ids.add(item.id)
        normalized = " ".join(item.raw_text.split())
        if normalized in raw_texts:
            raise ValidationError(f"第 {index} 条岗位记录与本次导入中的其他 JD 原文重复")
        raw_texts.add(normalized)
        parsed = urlparse(item.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidationError(f"第 {index} 条岗位记录的来源链接必须是有效的 http(s) 地址")
        if item.data_flag is DataFlag.REAL and item.posted_at is None:
            raise ValidationError(f"第 {index} 条 REAL 岗位记录缺少发布日期")

    if db.get(Job, payload.job_id) is None:
        db.add(Job(id=payload.job_id, name=payload.job_name))
        db.flush()

    existing_rows = db.query(JobPosting).filter(JobPosting.job_id == payload.job_id).all()
    existing_by_raw = {" ".join(row.raw_text.split()): row.id for row in existing_rows}
    created = updated = skipped_duplicates = pii_scrubbed = 0

    for item in payload.postings:
        normalized = " ".join(item.raw_text.split())
        duplicate_id = existing_by_raw.get(normalized)
        if duplicate_id is not None and duplicate_id != item.id:
            skipped_duplicates += 1
            continue
        raw_text, was_scrubbed = _scrub_pii(item.raw_text)
        if was_scrubbed:
            pii_scrubbed += 1
        fields = dict(
            job_id=payload.job_id,
            title=item.title,
            raw_text=raw_text,
            source_name=item.source_name,
            source_url=item.source_url,
            posted_at=item.posted_at,
            collected_at=datetime.now(timezone.utc),
            city=item.city,
            company_type=item.company_type,
            salary_text=item.salary_text,
            education_req=item.education_req,
            experience_req=item.experience_req,
            data_flag=item.data_flag,
            pii_scrubbed=was_scrubbed,
        )
        current = db.get(JobPosting, item.id)
        if current is None:
            db.add(JobPosting(id=item.id, **fields))
            created += 1
        else:
            for key, value in fields.items():
                setattr(current, key, value)
            updated += 1

    db.flush()
    result = JobMarketService(db).analyze(payload.job_id)
    db.commit()
    return JobPostingImportResponse(
        created=created,
        updated=updated,
        skipped_duplicates=skipped_duplicates,
        pii_scrubbed=pii_scrubbed,
        dashboard=result.dashboard,
    )


@router.post(
    "/{job_id}/analyze",
    response_model=JobMarketAnalyzeResponse,
    summary="从已导入 JD 重建技能需求统计",
    description=(
        "使用规范技能名/别名对 JD 原文做确定性精确匹配，保存原文证据片段，"
        "并重建全量和月度技能需求快照。不会调用 LLM。"
    ),
)
def analyze_job_market(
    job_id: str, db: Session = Depends(get_db)
) -> JobMarketAnalyzeResponse:
    result = JobMarketService(db).analyze(job_id)
    db.commit()
    return JobMarketAnalyzeResponse(
        dashboard=result.dashboard,
        extracted_skill_links=result.extracted_skill_links,
        snapshots_written=result.snapshots_written,
        reasoning_summary=(
            "技能排名和月度趋势由已导入 JD 的原文命中数/样本数确定性计算；"
            "每项技能均可下钻至岗位原文片段。"
        ),
        warnings=result.dashboard.data_quality.warnings,
    )


@router.get(
    "/{job_id}/dashboard",
    response_model=JobMarketDashboardRead,
    summary="岗位技能需求排名与趋势看板数据",
)
def get_job_market_dashboard(
    job_id: str,
    top_n: int = Query(default=10, ge=1, le=30),
    trend_skill_code: list[str] = Query(default=[]),
    city: str | None = Query(default=None, max_length=64),
    source: str | None = Query(default=None, max_length=128),
    title: str | None = Query(default=None, max_length=128),
    posted_from: datetime | None = None,
    posted_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> JobMarketDashboardRead:
    return JobMarketService(db).dashboard(
        job_id,
        top_n=top_n,
        trend_skill_codes=trend_skill_code or None,
        city=city,
        source=source,
        title=title,
        posted_from=posted_from,
        posted_to=posted_to,
    )
