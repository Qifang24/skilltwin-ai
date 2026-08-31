"""技能规范表接口。

`skill_code` 是全系统唯一的 join key，因此这里既提供查询，
也提供 `/normalize` —— 任何外部数据接入前都应先过一遍归一化。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.enums import SkillCategory, SkillStatus
from app.core.errors import NotFoundError
from app.models.knowledge import KnowledgeChunk
from app.models.ontology import Skill
from app.schemas.common import Page
from app.schemas.skill import (
    NormalizeRequest,
    NormalizeResponse,
    SkillDetail,
    SkillRead,
    SkillSourceRef,
)
from app.services.skill_normalizer import SkillNormalizer

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get(
    "",
    response_model=Page[SkillRead],
    summary="技能列表",
    description="全系统 join key 的规范技能表，可按类别与状态过滤。",
)
def list_skills(
    db: Session = Depends(get_db),
    category: SkillCategory | None = Query(default=None),
    status: SkillStatus | None = Query(default=SkillStatus.ACTIVE),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[SkillRead]:
    filters = []
    if category:
        filters.append(Skill.category == category)
    if status:
        filters.append(Skill.status == status)

    total = db.execute(
        select(func.count()).select_from(Skill).where(*filters)
    ).scalar_one()
    rows = (
        db.execute(
            select(Skill)
            .where(*filters)
            .order_by(Skill.category, Skill.skill_code)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return Page[SkillRead](
        items=[SkillRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{skill_code}",
    response_model=SkillDetail,
    summary="技能详情",
    description="含来源引用 —— 回答「这个技能点凭什么存在」，可下钻到标准原文页码。",
)
def get_skill(skill_code: str, db: Session = Depends(get_db)) -> SkillDetail:
    skill = db.get(Skill, skill_code)
    if skill is None:
        raise NotFoundError(
            f"未找到技能：{skill_code}", detail={"skill_code": skill_code}
        )

    sources: list[SkillSourceRef] = []
    for item in skill.evidence or []:
        chunk_id = item.get("chunk_id")
        chunk = db.get(KnowledgeChunk, chunk_id) if chunk_id else None
        doc = chunk.doc if chunk else None
        sources.append(
            SkillSourceRef(
                chunk_id=chunk_id or "",
                doc_id=doc.id if doc else None,
                source_name=doc.source_name if doc else None,
                standard_id=doc.standard_id if doc else None,
                page=item.get("page"),
                section=item.get("section"),
                quote=item.get("quote", ""),
            )
        )

    detail = SkillDetail.model_validate(skill)
    detail.sources = sources
    return detail


@router.post(
    "/normalize",
    response_model=NormalizeResponse,
    summary="技能名归一化",
    description=(
        "把任意技能写法解析为规范 skill_code。"
        "匹配不上时返回 unmatched —— 刻意不做模糊猜测，"
        "宁可交回人工确认，也不硬塞一个最像的技能污染能力表。"
    ),
)
def normalize_skills(
    payload: NormalizeRequest, db: Session = Depends(get_db)
) -> NormalizeResponse:
    normalizer = SkillNormalizer(db)
    matches = normalizer.normalize_many(payload.terms)
    matched = sum(1 for m in matches if m.is_matched)
    return NormalizeResponse(
        matches=matches,
        matched_count=matched,
        unmatched_count=len(matches) - matched,
    )
