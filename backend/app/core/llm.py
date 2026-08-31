"""LLM Provider 抽象层。

系统不锁死在任何一家模型上：上层只依赖 LLMProvider 接口，
换供应商 = 换一个实现 + 改 .env，业务代码零改动。

当前实现：
    OpenAICompatProvider —— DeepSeek / 通义千问 / OpenRouter / SiliconFlow 等
    EchoProvider         —— 测试专用，不发网络请求
    SparkProvider            —— 科大讯飞星火 HTTP / OpenAI-compatible API
    XingchenWorkflowProvider —— 科大讯飞星辰 Agent Workflow OpenAPI
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.core.config import LLMProviderName, settings
from app.core.errors import ConfigurationError, LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    """一次模型调用的结果。"""

    text: str
    model: str
    provider: str
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_truncated(self) -> bool:
        """输出被长度截断时，JSON 往往不完整，需要上层特殊处理。"""
        return self.finish_reason == "length"


class LLMProvider(ABC):
    """所有模型供应商的统一接口。"""

    #: 供应商标识，写入 llm_run.provider
    name: str = "base"

    @property
    @abstractmethod
    def model(self) -> str:
        """当前使用的模型标识，写入 llm_run.model。"""

    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """发起一次补全调用。

        json_mode=True 时请求供应商的 JSON 输出模式；不是所有模型都支持，
        因此**绝不能**把它当作输出一定合法的保证 —— 解析仍需容错。
        """


class OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容接口。一套代码通吃 DeepSeek / 通义 / OpenRouter / SiliconFlow。"""

    name = "openai_compat"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        # 用 `is not None` 而非 `or`：显式传入空串代表「明确没有 Key」，
        # 不能被静默回落成 settings 里的真实 Key（否则测试会意外打真实接口）
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._base_url = base_url if base_url is not None else settings.llm_base_url
        self._model = model if model is not None else settings.llm_model
        self._timeout = (
            timeout if timeout is not None else settings.llm_timeout_seconds
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.llm_max_retries
        )
        self._client_instance: Any = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def _client(self) -> Any:
        """延迟构造 HTTP 客户端，并把缺 Key 的检查推迟到真正要发请求时。

        这样 replay 模式（只读缓存、不发请求）在**没有 API Key 的机器上也能跑** ——
        比赛现场用备用笔记本演示时，这条路径必须成立。
        """
        if self._client_instance is None:
            if not self._api_key:
                raise ConfigurationError(
                    "LLM_API_KEY 未配置。请复制 .env.example 为 .env 并填入真实 Key"
                    "（Key 只能写在 .env，该文件已被 git 忽略）。"
                    "若只想离线演示已录制的结果，请设置 DEMO_MODE=replay。"
                )
            from openai import OpenAI

            self._client_instance = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._client_instance

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [m.to_dict() for m in messages],
            "temperature": (
                temperature if temperature is not None else settings.llm_temperature
            ),
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # 在 try 之外解析客户端：缺 Key 是**配置问题**，
        # 不该被下面的 except 包装成「模型调用失败」——那次调用压根没发生。
        client = self._client

        started = time.perf_counter()
        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as exc:
            # 部分模型（尤其经 OpenRouter 转发的）不支持 json_object，
            # 退回普通模式重试一次；解析层本来就要容错，不依赖此特性。
            if json_mode and _looks_like_json_mode_unsupported(exc):
                logger.warning(
                    "模型不支持 json_object，回退普通模式",
                    extra={"model": self._model},
                )
                kwargs.pop("response_format", None)
                try:
                    completion = client.chat.completions.create(**kwargs)
                except Exception as retry_exc:
                    raise LLMError(f"模型调用失败：{retry_exc}") from retry_exc
            else:
                raise LLMError(f"模型调用失败：{exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if not completion.choices:
            raise LLMError("模型返回了空的 choices")

        choice = completion.choices[0]
        usage = completion.usage
        return LLMResponse(
            text=choice.message.content or "",
            model=completion.model or self._model,
            provider=self.name,
            latency_ms=latency_ms,
            tokens_in=usage.prompt_tokens if usage else None,
            tokens_out=usage.completion_tokens if usage else None,
            finish_reason=choice.finish_reason,
        )


def _looks_like_json_mode_unsupported(exc: Exception) -> bool:
    text = str(exc).lower()
    return "response_format" in text or "json_object" in text


class SparkProvider(OpenAICompatProvider):
    """讯飞星火 HTTP Provider。

    星火 HTTP API 兼容 OpenAI SDK，但凭证是控制台提供的 ``APIPassword``。
    因此它不复用 ``LLM_API_KEY``，避免误把其他厂商或 WebSocket 凭证发送给讯飞。
    """

    name = "spark"

    def __init__(
        self,
        *,
        api_password: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._spark_api_password = (
            api_password if api_password is not None else settings.spark_api_password
        )
        super().__init__(
            api_key=self._spark_api_password,
            base_url=base_url if base_url is not None else settings.spark_base_url,
            model=model if model is not None else settings.spark_model,
            timeout=timeout,
            max_retries=max_retries,
        )

    @property
    def _client(self) -> Any:
        if self._client_instance is None:
            if not self._spark_api_password:
                raise ConfigurationError(
                    "SPARK_API_PASSWORD 未配置。请在讯飞开放平台控制台获取星火 HTTP "
                    "接口的 APIPassword 并仅写入 .env；不要填入 WebSocket 的 APIKey/APISecret。"
                )
            from openai import OpenAI

            self._client_instance = OpenAI(
                api_key=self._spark_api_password,
                base_url=self._base_url,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._client_instance


def _workflow_input(messages: list[Message]) -> str:
    """把标准聊天消息无损映射到工作流的单个起始输入参数。"""
    return "\n\n".join(
        f"[{message.role.upper()}]\n{message.content}" for message in messages
    )


class XingchenWorkflowProvider(LLMProvider):
    """讯飞星辰 Agent Workflow OpenAPI Provider。

    工作流由平台侧创建、调试和发布；本地系统仅传入完整上下文并记录输出。
    ``json_mode`` 不会被伪装成平台能力，结构化 Agent 仍由本项目的 Schema
    解析与一次修复机制保证。若工作流用于结构化 Agent，平台工作流必须保留 JSON 输出。
    """

    name = "xingchen_workflow"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        flow_id: str | None = None,
        base_url: str | None = None,
        input_parameter: str | None = None,
        uid: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.xingchen_api_key
        self._api_secret = (
            api_secret if api_secret is not None else settings.xingchen_api_secret
        )
        self._flow_id = flow_id if flow_id is not None else settings.xingchen_flow_id
        self._base_url = base_url if base_url is not None else settings.xingchen_base_url
        self._input_parameter = (
            input_parameter
            if input_parameter is not None
            else settings.xingchen_input_parameter
        )
        self._uid = uid if uid is not None else settings.xingchen_uid
        self._timeout = timeout if timeout is not None else settings.llm_timeout_seconds
        self._client_instance = client

    @property
    def model(self) -> str:
        return f"workflow:{self._flow_id or 'unconfigured'}"

    @property
    def _client(self) -> httpx.Client:
        if self._client_instance is None:
            self._client_instance = httpx.Client(timeout=self._timeout)
        return self._client_instance

    def _validate_configuration(self) -> None:
        missing = [
            name
            for name, value in {
                "XINGCHEN_API_KEY": self._api_key,
                "XINGCHEN_API_SECRET": self._api_secret,
                "XINGCHEN_FLOW_ID": self._flow_id,
                "XINGCHEN_INPUT_PARAMETER": self._input_parameter,
            }.items()
            if not value.strip()
        ]
        if missing:
            raise ConfigurationError(
                f"星辰 Workflow 配置缺失：{', '.join(missing)}。"
                "请先在星火智能体创作中心发布工作流，再把凭证只写入 .env。"
            )

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        del temperature, max_tokens, json_mode
        self._validate_configuration()
        body: dict[str, Any] = {
            "flow_id": self._flow_id,
            "parameters": {self._input_parameter: _workflow_input(messages)},
            "stream": False,
        }
        if self._uid:
            body["uid"] = self._uid

        started = time.perf_counter()
        try:
            response = self._client.post(
                self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}:{self._api_secret}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError(f"星辰 Workflow 调用失败：{exc}") from exc

        if not isinstance(payload, dict):
            raise LLMError("星辰 Workflow 返回不是 JSON 对象")
        code = payload.get("code")
        if code != 0:
            raise LLMError(
                f"星辰 Workflow 返回错误 code={code}：{payload.get('message', '未知错误')}"
            )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError("星辰 Workflow 返回缺少 choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise LLMError("星辰 Workflow choices 格式不正确")
        delta = first.get("delta")
        if not isinstance(delta, dict) or not isinstance(delta.get("content"), str):
            raise LLMError("星辰 Workflow 返回缺少 choices[0].delta.content")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}

        return LLMResponse(
            text=delta["content"],
            model=self.model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            tokens_in=_optional_int(usage.get("prompt_tokens")),
            tokens_out=_optional_int(usage.get("completion_tokens")),
            finish_reason=(
                first.get("finish_reason")
                if isinstance(first.get("finish_reason"), str)
                else None
            ),
            raw=payload,
        )


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


class EchoProvider(LLMProvider):
    """测试专用：不发任何网络请求，按预置脚本返回。

    scripted 用完后回落到 default_response，便于在测试中精确控制模型输出。
    """

    name = "echo"

    def __init__(
        self,
        scripted: list[str] | None = None,
        *,
        default_response: str = '{"echo": true}',
        model: str = "echo-model",
    ) -> None:
        self._scripted = list(scripted or [])
        self._default = default_response
        self._model = model
        #: 记录收到的全部调用，测试里可断言 prompt 内容
        self.calls: list[list[Message]] = []

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        text = self._scripted.pop(0) if self._scripted else self._default
        return LLMResponse(
            text=text,
            model=self._model,
            provider=self.name,
            latency_ms=0,
            tokens_in=sum(len(m.content) for m in messages),
            tokens_out=len(text),
            finish_reason="stop",
        )


def build_provider(name: LLMProviderName | None = None) -> LLMProvider:
    """按配置构造 Provider。"""
    provider_name = name or settings.llm_provider

    if provider_name is LLMProviderName.OPENAI_COMPAT:
        return OpenAICompatProvider()
    if provider_name is LLMProviderName.ECHO:
        return EchoProvider()
    if provider_name is LLMProviderName.SPARK:
        return SparkProvider()
    if provider_name is LLMProviderName.XINGCHEN_WORKFLOW:
        return XingchenWorkflowProvider()
    raise ConfigurationError(f"未知的 LLM_PROVIDER：{provider_name}")


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """进程内单例，避免每次请求重建 HTTP 客户端。"""
    global _provider
    if _provider is None:
        _provider = build_provider()
    return _provider


def reset_provider() -> None:
    """测试用：清空单例，使下次 get_provider 重新构造。"""
    global _provider
    _provider = None
