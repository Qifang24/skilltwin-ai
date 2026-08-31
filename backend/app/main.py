"""SkillTwin AI —— FastAPI 应用入口。

启动：
    cd backend && ../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
文档：
    http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.db import create_all
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging

setup_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_dirs()
    create_all()
    logger.info(
        "SkillTwin AI 启动",
        extra={
            "version": settings.app_version,
            "demo_mode": settings.demo_mode.value,
            "llm_provider": settings.llm_provider.value,
            "embedding_provider": settings.embedding_provider.value,
        },
    )
    yield
    logger.info("SkillTwin AI 关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "职业教育岗位能力与个性化实训智能体。\n\n"
        "**设计铁律**：LLM 只做「生成与解释」，不做「统计与排序」。"
        "所有百分比、Gap 数值、学习路径顺序均由确定性计算得出，可溯源到原始数据。"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["system"], summary="服务信息")
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
