"""Agent 基类。

刻意**不引入任何 Agent 框架**。一个 Agent 就是一个普通 Python 类：
    输入(typed) → 检索上下文 → 渲染 prompt → 调模型 → 结构校验 → 信封输出
校验失败时把 Pydantic 的报错原样喂回给模型，让它自己改一次。

关于 confidence 的口径（重要，别误读）：
    当前阶段它**只反映结构合法性**（是否一次通过 Schema 校验），
    不代表内容正确。事实层面的置信度要等 Phase 4 接入检索、
    Phase 13 接入 VerificationService 之后才有意义。
    在此之前，没有 sources 的输出一律标记 evidence_sufficiency=insufficient。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.enums import EvidenceSufficiency, LLMRunStatus
from app.core.errors import LLMOutputParseError
from app.core.json_utils import extract_json_object
from app.core.llm import Message
from app.core.llm_runner import LLMRunner, RunResult, get_runner
from app.core.logging import get_logger
from app.schemas.common import AgentEnvelope, SourceRef
from app.services.citation_verification_service import (
    CitationClaim,
    CitationVerificationService,
    VerificationResult,
)

logger = get_logger(__name__)

TIn = TypeVar("TIn")
TOut = TypeVar("TOut", bound=BaseModel)

#: 结构校验一次通过 / 修复后通过，对应的结构置信度
_CONFIDENCE_CLEAN = 0.9
_CONFIDENCE_REPAIRED = 0.7

_REPAIR_INSTRUCTION = """你上一条回复不符合要求的 JSON 结构，校验报错如下：

{errors}

请重新输出**完整的** JSON。要求：
1. 只输出 JSON 本身，不要任何解释文字，不要 markdown 代码块标记
2. 严格遵守前面给定的字段名与类型
3. 不要省略任何必填字段"""


class BaseAgent(ABC, Generic[TIn, TOut]):
    """所有 Agent 的统一骨架。"""

    #: 写入 llm_run.agent，也是缓存键的一部分
    name: str = "base"
    #: 输出的 Pydantic 模型，决定校验规则
    output_model: type[TOut]
    #: 是否请求供应商的 JSON 输出模式（不保证生效，解析层仍需容错）
    json_mode: bool = True
    #: 结构校验失败后允许模型自我修复的次数
    max_repair_attempts: int = 1
    temperature: float | None = None
    max_tokens: int | None = None
    #: 送进 prompt 的检索片段数量
    retrieve_top_n: int = 6

    def __init__(self, runner: LLMRunner | None = None, retriever=None) -> None:  # noqa: ANN001
        self._runner = runner
        self._retriever = retriever

    @property
    def runner(self) -> LLMRunner:
        return self._runner if self._runner is not None else get_runner()

    # ------------------------------------------------------------ 子类实现
    @abstractmethod
    def render_prompt(self, inp: TIn, sources: list[SourceRef]) -> list[Message]:
        """渲染 prompt。sources 为检索到的依据，需在 prompt 中以 [S1]…[Sn] 呈现。"""

    def retrieval_query(self, inp: TIn) -> str | None:
        """返回用于检索知识库的查询语句。

        子类实现它即自动获得 RAG 能力：检索结果会以 [S1]…[Sn] 形式
        传入 render_prompt，并作为 sources 出现在信封里。
        返回 None 表示该 Agent 不需要检索（例如纯格式转换类任务）。
        """
        return None

    def retrieve(self, db: Session, inp: TIn) -> list[SourceRef]:
        """混合检索支撑依据（dense + BM25 → RRF）。

        检索失败不应让整个 Agent 崩掉：拿不到依据时返回空列表，
        输出会被诚实标记为「证据不足」，而不是硬编一个答案。
        """
        query = self.retrieval_query(inp)
        if not query:
            return []

        from app.rag.retriever import HybridRetriever

        try:
            retriever = self._retriever or HybridRetriever()
            chunks = retriever.search(db, query, top_n=self.retrieve_top_n)
        except Exception as exc:
            logger.warning(
                "知识库检索失败，本次输出将标记为证据不足",
                extra={"agent": self.name, "error": str(exc)},
            )
            return []

        return [
            chunk.to_source_ref(marker=f"S{index}")
            for index, chunk in enumerate(chunks, start=1)
        ]

    def input_summary(self, inp: TIn) -> dict[str, Any]:
        """写入 llm_run.input_summary 的输入摘要（不含完整 prompt，避免膨胀）。"""
        if isinstance(inp, BaseModel):
            return inp.model_dump(mode="json")
        if isinstance(inp, dict):
            return dict(inp)
        return {"input": str(inp)[:500]}

    def reasoning_summary(self, parsed: TOut, sources: list[SourceRef]) -> str:
        """面向用户的简短依据说明。**不是**模型内部思维链。"""
        if sources:
            return f"依据知识库中 {len(sources)} 条相关内容生成，来源见下方引用。"
        return "本次生成未检索到知识库依据，结果仅供参考。"

    # ---------------------------------------------------------------- 主流程
    def run(self, db: Session, inp: TIn) -> AgentEnvelope[TOut]:
        sources = self.retrieve(db, inp)
        messages = self.render_prompt(inp, sources)
        summary = self.input_summary(inp)

        result = self.runner.run(
            db,
            agent=self.name,
            messages=messages,
            input_summary=summary,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            json_mode=self.json_mode,
        )

        parsed, final_run, repairs = self._parse_with_repair(
            db, messages, result, summary
        )

        LLMRunner.attach_output(
            db,
            final_run.llm_run_id,
            parsed.model_dump(mode="json"),
            repair_attempts=repairs,
        )

        verification = CitationVerificationService(db).verify_and_record(
            llm_run_id=final_run.llm_run_id,
            sources=sources,
            claims=self.citation_claims(parsed),
        )
        return self._build_envelope(parsed, final_run, verification, repairs)

    def citation_claims(self, parsed: TOut) -> list[CitationClaim]:
        """声明结构化输出中的结论及其证据范围。

        子类可按自己的字段覆盖（例如图谱节点按 evidence_markers 逐条落盘）；
        默认把整份结构化输出视作一条结论，并使用本次全部可验证来源。
        """
        return [CitationClaim(text=f"{self.name} 生成的结构化结论")]

    # ------------------------------------------------------------ 解析与修复
    def _parse_with_repair(
        self,
        db: Session,
        messages: list[Message],
        result: RunResult,
        summary: dict[str, Any],
    ) -> tuple[TOut, RunResult, int]:
        current = result
        conversation = list(messages)
        last_error: Exception | None = None

        for attempt in range(self.max_repair_attempts + 1):
            try:
                payload = extract_json_object(current.text)
                return self.output_model.model_validate(payload), current, attempt
            except (LLMOutputParseError, ValidationError) as exc:
                last_error = exc
                if attempt >= self.max_repair_attempts:
                    break

                logger.warning(
                    "模型输出结构校验失败，发起修复重试",
                    extra={
                        "agent": self.name,
                        "run_id": current.llm_run_id,
                        "attempt": attempt + 1,
                    },
                )
                conversation = [
                    *conversation,
                    Message(role="assistant", content=current.text),
                    Message(
                        role="user",
                        content=_REPAIR_INSTRUCTION.format(
                            errors=_format_errors(exc)
                        ),
                    ),
                ]
                current = self.runner.run(
                    db,
                    agent=self.name,
                    messages=conversation,
                    input_summary={**summary, "repair_attempt": attempt + 1},
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    json_mode=self.json_mode,
                )

        # 修复次数耗尽：把最后一次调用标记为解析失败，便于事后排查
        LLMRunner.attach_output(
            db,
            current.llm_run_id,
            {},
            repair_attempts=self.max_repair_attempts,
            status=LLMRunStatus.PARSE_FAILED,
        )
        raise LLMOutputParseError(
            f"{self.name} 的输出经 {self.max_repair_attempts} 次修复后仍不符合结构要求",
            detail={
                "agent": self.name,
                "llm_run_id": current.llm_run_id,
                "errors": _format_errors(last_error) if last_error else "",
            },
        )

    def _build_envelope(
        self,
        parsed: TOut,
        result: RunResult,
        verification: VerificationResult,
        repairs: int,
    ) -> AgentEnvelope[TOut]:
        warnings = list(verification.warnings)

        if verification.sources:
            sufficiency = EvidenceSufficiency.SUFFICIENT
        else:
            sufficiency = EvidenceSufficiency.INSUFFICIENT
            warnings.append("当前知识库暂无足够依据，本结论未经来源校验")

        if repairs:
            warnings.append(f"模型首次输出结构不合规，经 {repairs} 次修正后通过")
        if result.cache_hit:
            warnings.append("本次结果来自缓存回放，未发起真实模型调用")

        return AgentEnvelope[self.output_model](  # type: ignore[name-defined]
            result=parsed,
            reasoning_summary=self.reasoning_summary(parsed, verification.sources),
            sources=verification.sources,
            confidence=round(
                (_CONFIDENCE_CLEAN if repairs == 0 else _CONFIDENCE_REPAIRED)
                * verification.confidence,
                3,
            ),
            evidence_sufficiency=verification.evidence_sufficiency,
            ai_generated=True,
            llm_run_id=result.llm_run_id,
            warnings=warnings,
        )


def _format_errors(exc: Exception) -> str:
    """把 Pydantic 报错整理成模型看得懂的简明清单。"""
    if isinstance(exc, ValidationError):
        lines = []
        for error in exc.errors()[:12]:
            location = ".".join(str(part) for part in error["loc"]) or "(根)"
            lines.append(f"- 字段 {location}: {error['msg']}")
        return "\n".join(lines)
    return f"- {exc}"
