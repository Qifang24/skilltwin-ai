"""课程结构性覆盖与 Gap 接口（Phase 11）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.curriculum import CurriculumGapDashboardRead, CurriculumOptimizationRead
from app.services.curriculum_gap_service import CurriculumGapService
from app.services.curriculum_optimization_service import CurriculumOptimizationService

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


@router.get("/{job_id}/gap", response_model=CurriculumGapDashboardRead)
def get_curriculum_gap(job_id: str, plan_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> CurriculumGapDashboardRead:
    return CurriculumGapService(db).dashboard(job_id, plan_id)


@router.get("/{job_id}/optimization", response_model=CurriculumOptimizationRead)
def get_curriculum_optimization(job_id: str, plan_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> CurriculumOptimizationRead:
    return CurriculumOptimizationService(db).generate(job_id, plan_id)
