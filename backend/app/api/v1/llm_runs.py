"""模型调用审计接口 —— 可解释性的下钻入口。

任何 Agent 输出都会带 llm_run_id，用户点「查看依据」即可追到这里，
看到当时的输入摘要、原始输出、耗时、token 与引用记录。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.enums import LLMRunStatus
from app.core.errors import NotFoundError
from app.models.audit import LLMRun
from app.schemas.audit import LLMRunDetail, LLMRunSummary
from app.schemas.common import Page

router = APIRouter(prefix="/llm-runs", tags=["explainability"])


@router.get(
    "",
    response_model=Page[LLMRunSummary],
    summary="模型调用记录列表",
    description="按时间倒序返回调用记录，可按 agent 与状态过滤。",
)
def list_runs(
    db: Session = Depends(get_db),
    agent: str | None = Query(default=None, description="按 Agent 名称过滤"),
    status: LLMRunStatus | None = Query(default=None, description="按调用状态过滤"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[LLMRunSummary]:
    filters = []
    if agent:
        filters.append(LLMRun.agent == agent)
    if status:
        filters.append(LLMRun.status == status)

    total = db.execute(
        select(func.count()).select_from(LLMRun).where(*filters)
    ).scalar_one()

    rows = (
        db.execute(
            select(LLMRun)
            .where(*filters)
            .order_by(LLMRun.created_at.desc(), LLMRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return Page[LLMRunSummary](
        items=[LLMRunSummary.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{run_id}",
    response_model=LLMRunDetail,
    summary="模型调用详情",
    description="返回单次调用的完整记录，含原始输出与引用列表。",
)
def get_run(run_id: str, db: Session = Depends(get_db)) -> LLMRunDetail:
    run = db.execute(
        select(LLMRun)
        .options(selectinload(LLMRun.citations))
        .where(LLMRun.id == run_id)
    ).scalar_one_or_none()

    if run is None:
        raise NotFoundError(f"未找到调用记录：{run_id}", detail={"run_id": run_id})

    return LLMRunDetail.model_validate(run)
