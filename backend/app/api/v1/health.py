"""健康检查。

设计原则：**必须快**（不加载 embedding 模型、不发起 LLM 网络调用），
只做配置与连通性探测，用于启动自检和部署探针。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import LLMProviderName, settings
from app.core.db import get_db
from app.schemas.common import ComponentHealth, HealthResponse

router = APIRouter(tags=["system"])


def _check_database(db: Session) -> ComponentHealth:
    try:
        db.execute(text("SELECT 1"))
        engine_name = settings.database_url.split(":", 1)[0]
        return ComponentHealth(name="database", ok=True, detail=f"{engine_name} 连接正常")
    except Exception as exc:  # pragma: no cover - 依赖运行时环境
        return ComponentHealth(name="database", ok=False, detail=str(exc))


def _check_llm() -> ComponentHealth:
    """只看配置是否齐备，不发起真实调用。"""
    provider = settings.llm_provider
    if provider is LLMProviderName.ECHO:
        return ComponentHealth(name="llm", ok=True, detail="echo provider（测试模式，不调用远端）")
    if provider is LLMProviderName.OPENAI_COMPAT:
        if not settings.llm_api_key:
            return ComponentHealth(
                name="llm",
                ok=False,
                detail=(
                    "LLM_API_KEY 未配置，请在 Vercel 项目环境变量中填写"
                    if os.getenv("VERCEL") == "1"
                    else "LLM_API_KEY 未配置，请复制 .env.example 为 .env 并填入"
                ),
            )
        return ComponentHealth(
            name="llm", ok=True, detail=f"{settings.llm_model} @ {settings.llm_base_url}"
        )
    if provider is LLMProviderName.SPARK:
        missing = [
            k
            for k, v in {
                "SPARK_API_PASSWORD": settings.spark_api_password,
            }.items()
            if not v
        ]
        if missing:
            return ComponentHealth(
                name="llm", ok=False, detail=f"星火配置缺失：{', '.join(missing)}"
            )
        return ComponentHealth(
            name="llm", ok=True, detail=f"讯飞星火 {settings.spark_model} @ {settings.spark_base_url}"
        )
    if provider is LLMProviderName.XINGCHEN_WORKFLOW:
        missing = [
            k
            for k, v in {
                "XINGCHEN_FLOW_ID": settings.xingchen_flow_id,
                "XINGCHEN_API_KEY": settings.xingchen_api_key,
                "XINGCHEN_API_SECRET": settings.xingchen_api_secret,
                "XINGCHEN_INPUT_PARAMETER": settings.xingchen_input_parameter,
            }.items()
            if not v
        ]
        if missing:
            return ComponentHealth(
                name="llm", ok=False, detail=f"星辰 Workflow 配置缺失：{', '.join(missing)}"
            )
        return ComponentHealth(
            name="llm", ok=True, detail=f"星辰 Workflow 已配置（flow_id={settings.xingchen_flow_id}）"
        )
    return ComponentHealth(name="llm", ok=False, detail=f"未知 provider: {provider}")


def _check_embedding() -> ComponentHealth:
    """探测运行环境，不实际加载模型（加载需数秒且占显存）。"""
    if settings.retrieve_dense_top_k <= 0:
        return ComponentHealth(name="embedding", ok=True, detail="向量检索暂停；数据库 BM25 检索可用")
    if settings.embedding_provider.value == "openai_compat":
        base_url = settings.embedding_base_url or settings.llm_base_url
        if base_url.rstrip("/") == "https://ai-gateway.vercel.sh/v1":
            configured = bool(settings.embedding_api_key or settings.ai_gateway_api_key or os.getenv("VERCEL_OIDC_TOKEN"))
        else:
            configured = bool(settings.embedding_api_key or settings.llm_api_key)
        return ComponentHealth(
            name="embedding", ok=configured,
            detail=f"{settings.embedding_model} @ {base_url}" if configured else "Embedding 凭证未配置",
        )
    try:
        import torch

        device = (
            "cuda"
            if settings.embedding_device in ("auto", "cuda") and torch.cuda.is_available()
            else "cpu"
        )
        gpu = torch.cuda.get_device_name(0) if device == "cuda" else "CPU"
        return ComponentHealth(
            name="embedding",
            ok=True,
            detail=f"{settings.embedding_model} → {device} ({gpu})，未加载",
        )
    except Exception as exc:  # pragma: no cover
        return ComponentHealth(name="embedding", ok=False, detail=str(exc))


def _check_vector_store() -> ComponentHealth:
    if settings.vector_store == "sql":
        try:
            from app.rag.vector_store import build_vector_store

            count = build_vector_store().count()
            return ComponentHealth(name="vector_store", ok=True, detail=f"SQL 向量索引可用（{count} 条）")
        except Exception as exc:
            return ComponentHealth(name="vector_store", ok=False, detail=str(exc))
    try:
        import chromadb  # noqa: F401

        exists = settings.chroma_dir.exists()
        return ComponentHealth(
            name="vector_store",
            ok=True,
            detail=f"chroma 可用，持久化目录{'已就绪' if exists else '待创建'}",
        )
    except Exception as exc:  # pragma: no cover
        return ComponentHealth(name="vector_store", ok=False, detail=str(exc))


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康检查",
    description="返回各依赖组件状态。database 不通即为 degraded；"
    "LLM 未配置也标记为 degraded，但不影响离线功能。",
)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    components = [
        _check_database(db),
        _check_llm(),
        _check_embedding(),
        _check_vector_store(),
    ]
    return HealthResponse(
        status="ok" if all(c.ok for c in components) else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        demo_mode=settings.demo_mode.value,
        components=components,
    )
