"""岗位技能需求与趋势接口（Phase 10）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.models.job_market import JobPosting
from app.models.ontology import Job
from app.schemas.job_market import (
    JobMarketAnalyzeResponse,
    JobMarketDashboardRead,
    JobPostingImportRequest,
    JobPostingImportResponse,
    JobImportBatchRead,
    JobImportMappingUpdate,
    JobPostingRead,
)
from app.services.job_import_service import JobImportService
from app.services.job_market_service import JobMarketService

router = APIRouter(prefix="/job-market", tags=["job-market"])
import_router = APIRouter(prefix="/job-imports", tags=["job-imports"])


@router.get("/jobs", summary="可用于专业建设的岗位范围")
def list_market_jobs(db: Session = Depends(get_db)) -> list[dict[str, str]]:
    return [{"id": job.id, "name": job.name} for job in db.execute(select(Job).order_by(Job.name, Job.id)).scalars()]

@router.post("/import", response_model=JobPostingImportResponse, summary="导入并校验公开岗位 JD")
def import_job_postings(
    payload: JobPostingImportRequest, db: Session = Depends(get_db)
) -> JobPostingImportResponse:
    """兼容旧 JSON 契约；执行统一暂存、校验、去重、确认与重算服务。"""
    service = JobImportService(db)
    try:
        batch, dashboard = service.import_legacy_records(
            job_id=payload.job_id,
            job_name=payload.job_name,
            records=[item.model_dump(mode="json") for item in payload.postings],
        )
        rows = service.rows(batch.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    result = batch.result or {}
    return JobPostingImportResponse(
        created=int(result.get("created", 0)),
        updated=int(result.get("updated", 0)),
        skipped_duplicates=batch.duplicate_count,
        pii_scrubbed=sum(bool(row.normalized_data.get("pii_scrubbed")) for row in rows),
        dashboard=dashboard,
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


def _batch_payload(service: JobImportService, batch, *, preview_only: bool = False) -> dict:
    rows = service.rows(batch.id)
    if preview_only:
        rows = rows[:20]
    return {
        "id": batch.id, "job_id": batch.job_id, "job_name": batch.job_name,
        "filename": batch.filename, "status": batch.status, "headers": batch.headers,
        "field_mapping": batch.field_mapping, "total_rows": batch.total_rows,
        "success_count": batch.success_count, "failed_count": batch.failed_count,
        "duplicate_count": batch.duplicate_count, "filtered_count": batch.filtered_count,
        "result": batch.result,
        "rows": [{
            "row_number": row.row_number, "status": row.status,
            "normalized_data": row.normalized_data, "errors": row.errors,
            "warnings": row.warnings, "posting_id": row.posting_id,
        } for row in rows],
    }


@import_router.post("", response_model=JobImportBatchRead, status_code=201, summary="上传岗位文件并创建暂存批次")
async def create_job_import(
    file: UploadFile = File(...),
    job_id: str = Form(...),
    job_name: str = Form(...),
    db: Session = Depends(get_db),
) -> dict:
    service = JobImportService(db)
    batch = service.create(filename=file.filename or "postings.csv", content=await file.read(), job_id=job_id, job_name=job_name)
    db.commit()
    return _batch_payload(service, batch, preview_only=True)


@import_router.patch("/{batch_id}/mapping", response_model=JobImportBatchRead)
def update_job_import_mapping(batch_id: str, payload: JobImportMappingUpdate, db: Session = Depends(get_db)) -> dict:
    service = JobImportService(db)
    batch = service.update_mapping(batch_id, payload.mapping)
    db.commit()
    return _batch_payload(service, batch, preview_only=True)


@import_router.get("/{batch_id}/preview", response_model=JobImportBatchRead)
def preview_job_import(batch_id: str, db: Session = Depends(get_db)) -> dict:
    service = JobImportService(db)
    return _batch_payload(service, service.get(batch_id), preview_only=True)


@import_router.post("/{batch_id}/confirm", response_model=JobImportBatchRead)
def confirm_job_import(batch_id: str, db: Session = Depends(get_db)) -> dict:
    service = JobImportService(db)
    try:
        batch = service.confirm(batch_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _batch_payload(service, batch)


@import_router.get("/{batch_id}/result", response_model=JobImportBatchRead)
def get_job_import_result(batch_id: str, db: Session = Depends(get_db)) -> dict:
    service = JobImportService(db)
    return _batch_payload(service, service.get(batch_id))


@router.get("/{job_id}/postings", response_model=list[JobPostingRead])
def list_job_postings(
    job_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    postings = list(db.execute(select(JobPosting).options(selectinload(JobPosting.skills)).where(JobPosting.job_id == job_id).order_by(JobPosting.posted_at.desc(), JobPosting.id).offset(offset).limit(limit)).scalars())
    return [{
        "id": p.id, "job_id": p.job_id, "title": p.title, "company_name": p.company_name,
        "company_type": p.company_type, "city": p.city, "raw_text": p.raw_text,
        "source_name": p.source_name, "source_url": p.source_url, "posted_at": p.posted_at,
        "data_flag": p.data_flag, "pii_scrubbed": p.pii_scrubbed,
        "source_record_id": p.source_record_id,
        "skills": [{"skill_code": s.skill_code, "evidence_span": s.evidence_span, "confidence": s.confidence} for s in p.skills],
    } for p in postings]


@router.get("/{job_id}/postings/{posting_id}", response_model=JobPostingRead)
def get_job_posting(job_id: str, posting_id: str, db: Session = Depends(get_db)) -> dict:
    from app.core.errors import NotFoundError
    p = db.execute(select(JobPosting).options(selectinload(JobPosting.skills)).where(JobPosting.job_id == job_id, JobPosting.id == posting_id)).scalar_one_or_none()
    if p is None:
        raise NotFoundError(f"未找到岗位记录：{posting_id}")
    return {
        "id": p.id, "job_id": p.job_id, "title": p.title, "company_name": p.company_name,
        "company_type": p.company_type, "city": p.city, "raw_text": p.raw_text,
        "source_name": p.source_name, "source_url": p.source_url, "posted_at": p.posted_at,
        "data_flag": p.data_flag, "pii_scrubbed": p.pii_scrubbed, "source_record_id": p.source_record_id,
        "skills": [{"skill_code": s.skill_code, "evidence_span": s.evidence_span, "confidence": s.confidence} for s in p.skills],
    }
