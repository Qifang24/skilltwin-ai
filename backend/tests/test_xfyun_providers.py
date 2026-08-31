"""讯飞星火 / 星辰适配的离线契约测试。"""

from __future__ import annotations

import json

import httpx
import pytest

from app.api.v1.health import _check_llm
from app.core.config import LLMProviderName, settings
from app.core.errors import ConfigurationError, LLMError
from app.core.llm import (
    Message,
    SparkProvider,
    XingchenWorkflowProvider,
    build_provider,
)


def test_spark_provider_uses_a_separate_http_api_password() -> None:
    provider = SparkProvider(
        api_password="spark-http-password",
        base_url="https://spark-api-open.xf-yun.com/v1",
        model="4.0Ultra",
    )

    assert provider.name == "spark"
    assert provider.model == "4.0Ultra"


def test_spark_provider_rejects_missing_http_api_password() -> None:
    provider = SparkProvider(api_password="")

    with pytest.raises(ConfigurationError, match="SPARK_API_PASSWORD"):
        provider.complete([Message(role="user", content="你好")])


def test_xingchen_workflow_posts_official_non_stream_shape() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "Success",
                "id": "workflow-session-id",
                "choices": [
                    {
                        "delta": {"role": "assistant", "content": "已根据当前任务给出建议。"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            },
        )

    provider = XingchenWorkflowProvider(
        api_key="workflow-key",
        api_secret="workflow-secret",
        flow_id="flow-123",
        uid="anonymous-student-01",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.complete(
        [
            Message(role="system", content="你是职业教育辅导员。"),
            Message(role="user", content="怎样检查标注质量？"),
        ]
    )
    expected_input = "\n".join(
        ["[SYSTEM]", "你是职业教育辅导员。", "", "[USER]", "怎样检查标注质量？"]
    )

    assert seen["url"] == "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions"
    assert seen["authorization"] == "Bearer workflow-key:workflow-secret"
    assert seen["body"] == {
        "flow_id": "flow-123",
        "uid": "anonymous-student-01",
        "parameters": {"AGENT_USER_INPUT": expected_input},
        "stream": False,
    }
    assert result.provider == "xingchen_workflow"
    assert result.model == "workflow:flow-123"
    assert result.text == "已根据当前任务给出建议。"
    assert result.tokens_in == 12
    assert result.tokens_out == 8


def test_xingchen_workflow_rejects_unpublished_or_error_response() -> None:
    provider = XingchenWorkflowProvider(
        api_key="key",
        api_secret="secret",
        flow_id="draft-flow",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={"code": 20805, "message": "flow id 状态为草稿，请发布"},
                )
            )
        ),
    )

    with pytest.raises(LLMError, match="code=20805"):
        provider.complete([Message(role="user", content="测试")])


def test_xingchen_workflow_rejects_missing_configuration_without_network() -> None:
    provider = XingchenWorkflowProvider(api_key="", api_secret="", flow_id="")

    with pytest.raises(ConfigurationError, match="XINGCHEN_API_KEY"):
        provider.complete([Message(role="user", content="测试")])


def test_provider_factory_builds_both_xfyun_adapters() -> None:
    assert isinstance(build_provider(LLMProviderName.SPARK), SparkProvider)
    assert isinstance(
        build_provider(LLMProviderName.XINGCHEN_WORKFLOW), XingchenWorkflowProvider
    )


def test_health_reports_the_right_xfyun_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", LLMProviderName.SPARK)
    monkeypatch.setattr(settings, "spark_api_password", "")
    assert "SPARK_API_PASSWORD" in _check_llm().detail

    monkeypatch.setattr(settings, "spark_api_password", "configured-password")
    assert _check_llm().ok is True

    monkeypatch.setattr(settings, "llm_provider", LLMProviderName.XINGCHEN_WORKFLOW)
    monkeypatch.setattr(settings, "xingchen_flow_id", "flow-123")
    monkeypatch.setattr(settings, "xingchen_api_key", "key")
    monkeypatch.setattr(settings, "xingchen_api_secret", "")
    assert "XINGCHEN_API_SECRET" in _check_llm().detail

    monkeypatch.setattr(settings, "xingchen_api_secret", "secret")
    assert _check_llm().ok is True
