"""模型调用的审计与缓存层。

所有模型调用都必须经由 LLMRunner，不允许业务代码直接持有 Provider 调用。
这一层同时解决三件事：

  可复现  每次调用的输入摘要、原始输出、耗时、token 全量落盘到 llm_run
  可省钱  record 模式下相同 prompt 命中缓存，开发期不重复烧 token
  可演示  replay 模式只读缓存、不发网络请求，断网也能完整演示

三种模式（DEMO_MODE）：
    live    总是真实调用。仍然落盘。
    record  优先命中缓存，未命中才真实调用。开发期推荐。
    replay  只读缓存，未命中直接报错。演示当天用。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DemoMode, settings
from app.core.enums import LLMRunStatus
from app.core.errors import LLMError
from app.core.llm import LLMProvider, LLMResponse, Message, get_provider
from app.core.logging import get_logger
from app.models.audit import LLMRun

logger = get_logger(__name__)


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:20]}"


def compute_prompt_hash(
    *,
    agent: str,
    provider: str,
    model: str,
    messages: list[Message],
    temperature: float,
    json_mode: bool,
) -> str:
    """缓存键。

    刻意把 agent / provider / model / temperature / json_mode 全部纳入：
    换模型或改温度后就应该重新调用，而不是拿旧结果糊弄。
    """
    payload = json.dumps(
        {
            "agent": agent,
            "provider": provider,
            "model": model,
            "temperature": round(temperature, 4),
            "json_mode": json_mode,
            "messages": [m.to_dict() for m in messages],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class RunResult:
    """一次 run 的结果，附带审计信息。"""

    response: LLMResponse
    llm_run_id: str
    cache_hit: bool

    @property
    def text(self) -> str:
        return self.response.text


class LLMRunner:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        demo_mode: DemoMode | None = None,
    ) -> None:
        self._provider = provider
        self._demo_mode = demo_mode

    @property
    def provider(self) -> LLMProvider:
        # 延迟到首次使用才构造：缺 Key 时不应在 import 阶段就炸掉整个应用
        if self._provider is None:
            self._provider = get_provider()
        return self._provider

    @property
    def demo_mode(self) -> DemoMode:
        return self._demo_mode if self._demo_mode is not None else settings.demo_mode

    # ------------------------------------------------------------------ 缓存
    def _lookup_cache(self, db: Session, prompt_hash: str) -> LLMRun | None:
        stmt = (
            select(LLMRun)
            .where(
                LLMRun.prompt_hash == prompt_hash,
                LLMRun.status == LLMRunStatus.SUCCESS,
                LLMRun.raw_output.is_not(None),
            )
            .order_by(LLMRun.created_at.desc())
            .limit(1)
        )
        return db.execute(stmt).scalars().first()

    # -------------------------------------------------------------------- 主流程
    def run(
        self,
        db: Session,
        *,
        agent: str,
        messages: list[Message],
        input_summary: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> RunResult:
        """执行一次模型调用（或从缓存回放），并把过程落盘。"""
        provider = self.provider
        effective_temp = (
            temperature if temperature is not None else settings.llm_temperature
        )
        prompt_hash = compute_prompt_hash(
            agent=agent,
            provider=provider.name,
            model=provider.model,
            messages=messages,
            temperature=effective_temp,
            json_mode=json_mode,
        )
        summary = dict(input_summary or {})
        mode = self.demo_mode

        # ---- 缓存路径（replay 必走，record 优先走）----
        if mode in (DemoMode.REPLAY, DemoMode.RECORD):
            cached = self._lookup_cache(db, prompt_hash)
            if cached is not None:
                logger.info(
                    "命中缓存，未发起真实调用",
                    extra={"agent": agent, "origin_run_id": cached.id, "mode": mode.value},
                )
                summary["origin_run_id"] = cached.id
                return self._persist(
                    db,
                    agent=agent,
                    provider_name=cached.provider,
                    model=cached.model,
                    prompt_hash=prompt_hash,
                    input_summary=summary,
                    raw_output=cached.raw_output,
                    output_json=cached.output_json,
                    latency_ms=0,
                    tokens_in=cached.tokens_in,
                    tokens_out=cached.tokens_out,
                    status=LLMRunStatus.SUCCESS,
                    cache_hit=True,
                )
            if mode is DemoMode.REPLAY:
                raise LLMError(
                    "回放模式下未找到该请求的缓存记录。"
                    "请先在 live 或 record 模式下跑一遍以录制结果，或改回 DEMO_MODE=live。",
                    detail={"agent": agent, "prompt_hash": prompt_hash},
                )

        # ---- 真实调用 ----
        try:
            response = provider.complete(
                messages,
                temperature=effective_temp,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
        except Exception as exc:
            # 失败同样入库：排查线上问题时，没记录的失败等于没发生过
            self._persist(
                db,
                agent=agent,
                provider_name=provider.name,
                model=provider.model,
                prompt_hash=prompt_hash,
                input_summary=summary,
                raw_output=None,
                output_json=None,
                latency_ms=None,
                tokens_in=None,
                tokens_out=None,
                status=LLMRunStatus.PROVIDER_ERROR,
                cache_hit=False,
                error_message=str(exc)[:2000],
            )
            raise

        result = self._persist(
            db,
            agent=agent,
            provider_name=response.provider,
            model=response.model,
            prompt_hash=prompt_hash,
            input_summary=summary,
            raw_output=response.text,
            output_json=None,  # 结构化结果由 Agent 校验通过后回填
            latency_ms=response.latency_ms,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            status=LLMRunStatus.SUCCESS,
            cache_hit=False,
        )
        logger.info(
            "模型调用完成",
            extra={
                "agent": agent,
                "run_id": result.llm_run_id,
                "model": response.model,
                "latency_ms": response.latency_ms,
                "tokens_out": response.tokens_out,
            },
        )
        return result

    # -------------------------------------------------------------------- 落盘
    def _persist(
        self,
        db: Session,
        *,
        agent: str,
        provider_name: str,
        model: str,
        prompt_hash: str,
        input_summary: dict[str, Any],
        raw_output: str | None,
        output_json: dict[str, Any] | None,
        latency_ms: int | None,
        tokens_in: int | None,
        tokens_out: int | None,
        status: LLMRunStatus,
        cache_hit: bool,
        error_message: str | None = None,
    ) -> RunResult:
        run = LLMRun(
            id=new_run_id(),
            agent=agent,
            provider=provider_name,
            model=model,
            prompt_hash=prompt_hash,
            input_summary=input_summary,
            output_json=output_json,
            raw_output=raw_output,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            status=status,
            cache_hit=cache_hit,
            error_message=error_message,
        )
        db.add(run)
        db.commit()

        return RunResult(
            response=LLMResponse(
                text=raw_output or "",
                model=model,
                provider=provider_name,
                latency_ms=latency_ms or 0,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            ),
            llm_run_id=run.id,
            cache_hit=cache_hit,
        )

    # ------------------------------------------------------- 供 Agent 回填结果
    @staticmethod
    def attach_output(
        db: Session,
        run_id: str,
        output_json: dict[str, Any],
        *,
        repair_attempts: int = 0,
        status: LLMRunStatus = LLMRunStatus.SUCCESS,
    ) -> None:
        """Agent 完成结构校验后，把规范化结果回填到 llm_run。

        缓存回放依赖 raw_output，而下游展示与复现依赖 output_json，
        因此两者都要留。
        """
        run = db.get(LLMRun, run_id)
        if run is None:
            return
        run.output_json = output_json
        run.repair_attempts = repair_attempts
        run.status = status
        db.commit()


_runner: LLMRunner | None = None


def get_runner() -> LLMRunner:
    global _runner
    if _runner is None:
        _runner = LLMRunner()
    return _runner


def reset_runner() -> None:
    """测试用。"""
    global _runner
    _runner = None
