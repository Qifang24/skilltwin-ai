"""v1 API 路由汇总。

后续各 Phase 在此挂载：
  Phase 3  skills      Phase 5  graphs      Phase 7  training_tasks
  Phase 4  knowledge   Phase 9  students / learning_paths    Phase 10 jobs
  Phase 12 tutor
"""

from fastapi import APIRouter

from app.api.v1 import (
    curriculum,
    graphs,
    health,
    job_market,
    knowledge,
    learning_paths,
    llm_runs,
    skills,
    students,
    training_tasks,
    tutor,
    user_testing,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(skills.router)
api_router.include_router(graphs.router)
api_router.include_router(job_market.router)
api_router.include_router(job_market.import_router)
api_router.include_router(curriculum.router)
api_router.include_router(curriculum.import_router)
api_router.include_router(training_tasks.router)
api_router.include_router(students.router)
api_router.include_router(learning_paths.router)
api_router.include_router(tutor.router)
api_router.include_router(user_testing.router)
api_router.include_router(knowledge.router)
api_router.include_router(llm_runs.router)

__all__ = ["api_router"]
