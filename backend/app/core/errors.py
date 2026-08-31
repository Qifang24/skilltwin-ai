"""统一异常体系与 FastAPI 异常处理器。

所有业务异常都继承 SkillTwinError，落到 HTTP 层时形成一致的错误信封：
    {"error": {"code": "...", "message": "...", "detail": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class SkillTwinError(Exception):
    """业务异常基类。"""

    code = "internal_error"
    status_code = 500
    message = "服务内部错误"

    def __init__(
        self, message: str | None = None, detail: dict[str, Any] | None = None
    ) -> None:
        self.message = message or self.message
        self.detail = detail or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "detail": self.detail,
            }
        }


class NotFoundError(SkillTwinError):
    code = "not_found"
    status_code = 404
    message = "资源不存在"


class ValidationError(SkillTwinError):
    code = "validation_error"
    status_code = 422
    message = "请求参数不合法"


class ConflictError(SkillTwinError):
    code = "conflict"
    status_code = 409
    message = "资源状态冲突"


class ConfigurationError(SkillTwinError):
    code = "configuration_error"
    status_code = 500
    message = "服务配置缺失或不正确"


class LLMError(SkillTwinError):
    code = "llm_error"
    status_code = 502
    message = "模型调用失败"


class LLMOutputParseError(LLMError):
    code = "llm_output_parse_error"
    message = "模型输出不符合约定结构"


class InsufficientEvidenceError(SkillTwinError):
    """知识库缺少支撑依据时抛出——不允许让模型自由编造。"""

    code = "insufficient_evidence"
    status_code = 200  # 这是正常业务状态，不是故障
    message = "当前知识库暂无足够依据"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SkillTwinError)
    async def _handle_skilltwin(_: Request, exc: SkillTwinError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("业务异常", extra={"code": exc.code, "detail": exc.detail})
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "请求参数不合法",
                    "detail": {"errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未捕获异常")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "服务内部错误",
                    "detail": {"type": type(exc).__name__},
                }
            },
        )
