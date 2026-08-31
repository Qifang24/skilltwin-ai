"""LLMRunner 的审计、缓存与回放测试。

重点验证 replay 模式：比赛演示当天断网也要能跑，这条链路不能靠运气。
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import DemoMode
from app.core.enums import LLMRunStatus
from app.core.errors import LLMError
from app.core.llm import EchoProvider, LLMProvider, LLMResponse, Message
from app.core.llm_runner import LLMRunner, compute_prompt_hash
from app.models.audit import LLMRun

MESSAGES = [Message(role="user", content="AI数据标注工程师需要哪些技能？")]


def _runner(provider: LLMProvider, mode: DemoMode) -> LLMRunner:
    return LLMRunner(provider=provider, demo_mode=mode)


def _count_runs(db: Session) -> int:
    return db.execute(select(func.count()).select_from(LLMRun)).scalar_one()


# ------------------------------------------------------------------ 基本落盘


def test_live_call_is_persisted(db: Session) -> None:
    provider = EchoProvider(['{"skills": ["python"]}'])
    result = _runner(provider, DemoMode.LIVE).run(
        db, agent="test_agent", messages=MESSAGES, input_summary={"job": "annot"}
    )

    assert result.cache_hit is False
    assert result.text == '{"skills": ["python"]}'

    run = db.get(LLMRun, result.llm_run_id)
    assert run is not None
    assert run.agent == "test_agent"
    assert run.provider == "echo"
    assert run.status is LLMRunStatus.SUCCESS
    assert run.raw_output == '{"skills": ["python"]}'
    assert run.input_summary == {"job": "annot"}


def test_live_mode_never_uses_cache(db: Session) -> None:
    """live 的语义就是每次真调，不能偷偷走缓存。"""
    provider = EchoProvider(['{"n": 1}', '{"n": 2}'])
    runner = _runner(provider, DemoMode.LIVE)

    first = runner.run(db, agent="a", messages=MESSAGES)
    second = runner.run(db, agent="a", messages=MESSAGES)

    assert first.text == '{"n": 1}'
    assert second.text == '{"n": 2}'  # 第二次拿到的是新结果，说明真的又调了
    assert len(provider.calls) == 2
    assert second.cache_hit is False


# -------------------------------------------------------------------- 缓存


def test_record_mode_hits_cache_on_second_call(db: Session) -> None:
    provider = EchoProvider(['{"n": 1}', '{"n": 2}'])
    runner = _runner(provider, DemoMode.RECORD)

    first = runner.run(db, agent="a", messages=MESSAGES)
    second = runner.run(db, agent="a", messages=MESSAGES)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.text == '{"n": 1}'      # 复用首次结果
    assert len(provider.calls) == 1        # 只发生了一次真实调用


def test_cache_hit_records_origin_run(db: Session) -> None:
    """缓存命中也要留痕，并能追回最初那次真实生成。"""
    provider = EchoProvider(['{"n": 1}'])
    runner = _runner(provider, DemoMode.RECORD)

    first = runner.run(db, agent="a", messages=MESSAGES)
    second = runner.run(db, agent="a", messages=MESSAGES)

    cached_run = db.get(LLMRun, second.llm_run_id)
    assert cached_run is not None
    assert cached_run.cache_hit is True
    assert cached_run.input_summary["origin_run_id"] == first.llm_run_id


def test_different_prompt_misses_cache(db: Session) -> None:
    provider = EchoProvider(['{"n": 1}', '{"n": 2}'])
    runner = _runner(provider, DemoMode.RECORD)

    runner.run(db, agent="a", messages=MESSAGES)
    other = runner.run(db, agent="a", messages=[Message(role="user", content="别的问题")])

    assert other.cache_hit is False
    assert len(provider.calls) == 2


def test_different_agent_misses_cache(db: Session) -> None:
    """agent 是缓存键的一部分：同样的话由不同 Agent 问，语义不同。"""
    provider = EchoProvider(['{"n": 1}', '{"n": 2}'])
    runner = _runner(provider, DemoMode.RECORD)

    runner.run(db, agent="agent_a", messages=MESSAGES)
    other = runner.run(db, agent="agent_b", messages=MESSAGES)

    assert other.cache_hit is False


def test_prompt_hash_is_stable_and_sensitive() -> None:
    base = dict(
        agent="a", provider="echo", model="m", messages=MESSAGES,
        temperature=0.2, json_mode=True,
    )
    assert compute_prompt_hash(**base) == compute_prompt_hash(**base)
    assert compute_prompt_hash(**{**base, "temperature": 0.9}) != compute_prompt_hash(**base)
    assert compute_prompt_hash(**{**base, "model": "other"}) != compute_prompt_hash(**base)


# -------------------------------------------------------------------- 回放


def test_replay_serves_from_cache_without_calling_provider(db: Session) -> None:
    """演示当天的关键路径：先录制，再断网回放。"""
    recorder = EchoProvider(['{"answer": "已录制的真实结果"}'])
    _runner(recorder, DemoMode.RECORD).run(db, agent="a", messages=MESSAGES)

    # 换一个「一调用就炸」的 Provider，模拟断网
    class ExplodingProvider(LLMProvider):
        name = "echo"

        @property
        def model(self) -> str:
            return "echo-model"

        def complete(self, messages, **kwargs) -> LLMResponse:  # noqa: ANN001, ANN003
            raise AssertionError("回放模式下不应发起任何真实调用")

    replayed = _runner(ExplodingProvider(), DemoMode.REPLAY).run(
        db, agent="a", messages=MESSAGES
    )
    assert replayed.cache_hit is True
    assert replayed.text == '{"answer": "已录制的真实结果"}'


def test_replay_without_cache_fails_loudly(db: Session) -> None:
    """没录过就回放，必须明确报错，不能悄悄编一个结果出来。"""
    with pytest.raises(LLMError, match="未找到该请求的缓存记录"):
        _runner(EchoProvider(), DemoMode.REPLAY).run(
            db, agent="never_recorded", messages=MESSAGES
        )


def test_replay_works_without_api_key(db: Session) -> None:
    """比赛现场用没配 Key 的备用机演示：replay 必须照常出结果。

    构造 Provider 时不能因缺 Key 就报错 —— 缓存命中路径根本用不到 HTTP 客户端。
    """
    from app.core.llm import OpenAICompatProvider

    recorder = EchoProvider(['{"answer": "已录制"}'])
    keyless = OpenAICompatProvider(api_key="", model="deepseek/deepseek-chat")
    # 用同一身份录制，模拟「同一台机器、同样配置，只是没网也没 Key」
    recorder.name = keyless.name  # type: ignore[misc]
    recorder._model = keyless.model  # type: ignore[attr-defined]

    _runner(recorder, DemoMode.RECORD).run(db, agent="a", messages=MESSAGES)
    replayed = _runner(keyless, DemoMode.REPLAY).run(db, agent="a", messages=MESSAGES)

    assert replayed.cache_hit is True
    assert replayed.text == '{"answer": "已录制"}'


def test_missing_key_still_fails_on_real_call() -> None:
    """但真要发请求时，缺 Key 必须明确报错，不能静默降级。"""
    from app.core.errors import ConfigurationError
    from app.core.llm import OpenAICompatProvider

    provider = OpenAICompatProvider(api_key="")
    with pytest.raises(ConfigurationError, match="LLM_API_KEY 未配置"):
        provider.complete([Message(role="user", content="hi")])


# -------------------------------------------------------------------- 失败


def test_provider_failure_is_persisted_and_reraised(db: Session) -> None:
    """失败也要入库 —— 没记录的失败等于没发生过。"""

    class FailingProvider(LLMProvider):
        name = "failing"

        @property
        def model(self) -> str:
            return "broken-model"

        def complete(self, messages, **kwargs) -> LLMResponse:  # noqa: ANN001, ANN003
            raise LLMError("连接超时")

    with pytest.raises(LLMError, match="连接超时"):
        _runner(FailingProvider(), DemoMode.LIVE).run(db, agent="a", messages=MESSAGES)

    run = db.execute(select(LLMRun)).scalars().one()
    assert run.status is LLMRunStatus.PROVIDER_ERROR
    assert "连接超时" in (run.error_message or "")
    assert run.raw_output is None


def test_failed_run_is_not_used_as_cache(db: Session) -> None:
    """失败记录绝不能被当成缓存回放出来。"""

    class FailingProvider(LLMProvider):
        name = "failing"

        @property
        def model(self) -> str:
            return "broken-model"

        def complete(self, messages, **kwargs) -> LLMResponse:  # noqa: ANN001, ANN003
            raise LLMError("boom")

    with pytest.raises(LLMError):
        _runner(FailingProvider(), DemoMode.LIVE).run(db, agent="a", messages=MESSAGES)

    assert _count_runs(db) == 1
    with pytest.raises(LLMError, match="未找到该请求的缓存记录"):
        _runner(EchoProvider(), DemoMode.REPLAY).run(db, agent="a", messages=MESSAGES)


# -------------------------------------------------------------------- 回填


def test_attach_output_writes_structured_result(db: Session) -> None:
    provider = EchoProvider(['{"skills": ["python"]}'])
    result = _runner(provider, DemoMode.LIVE).run(db, agent="a", messages=MESSAGES)

    LLMRunner.attach_output(db, result.llm_run_id, {"skills": ["python"]}, repair_attempts=1)

    run = db.get(LLMRun, result.llm_run_id)
    assert run is not None
    assert run.output_json == {"skills": ["python"]}
    assert run.repair_attempts == 1
    # raw_output 必须保留：缓存回放依赖它
    assert run.raw_output == '{"skills": ["python"]}'
