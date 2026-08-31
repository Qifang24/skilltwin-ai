"""岗位技能需求与趋势接口（Phase 10）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.job_market import JobMarketAnalyzeResponse, JobMarketDashboardRead
from app.services.job_market_service import JobMarketService

router = APIRouter(prefix="/job-market", tags=["job-market"])


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
    db: Session = Depends(get_db),
) -> JobMarketDashboardRead:
    return JobMarketService(db).dashboard(
        job_id,
        top_n=top_n,
        trend_skill_codes=trend_skill_code or None,
    )
