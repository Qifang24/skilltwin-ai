"""LLM 链路冒烟测试 —— 用真实模型验证 Phase 2 的三条能力。

    python scripts/smoke_llm.py

依次验证：
    1. 真实调用     结构化输出通过 Pydantic 校验
    2. 缓存命中     相同请求不再烧 token
    3. 断网回放     replay 模式下换成「一调用就炸」的 Provider 仍能出结果

会真实消耗少量 token（约 300~600），并向 llm_run 写入记录。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pydantic import BaseModel, Field  # noqa: E402

from app.agents.base import BaseAgent  # noqa: E402
from app.core.config import DemoMode, settings  # noqa: E402
from app.core.db import create_all, session_scope  # noqa: E402
from app.core.llm import LLMProvider, LLMResponse, Message, build_provider  # noqa: E402
from app.core.llm_runner import LLMRunner  # noqa: E402
from app.core.logging import force_utf8_stdio, setup_logging  # noqa: E402
from app.models.audit import LLMRun  # noqa: E402
from app.schemas.common import SourceRef  # noqa: E402


# ---------------------------------------------------------------- 输出结构
class ExtractedSkill(BaseModel):
    name: str = Field(description="技能名称")
    category: str = Field(description="所属类别")
    reason: str = Field(description="为什么该岗位需要它")


class SkillExtraction(BaseModel):
    job: str
    skills: list[ExtractedSkill] = Field(min_length=3, max_length=6)


PROMPT = """你是职业教育岗位分析专家。请分析岗位「{job}」所需的核心技能。

只输出 JSON，不要任何解释文字，不要 markdown 代码块标记。格式：
{{
  "job": "岗位名称",
  "skills": [
    {{"name": "技能名称", "category": "类别", "reason": "该岗位为何需要它"}}
  ]
}}

要求 skills 包含 3 到 6 项。"""


class SkillExtractionAgent(BaseAgent[str, SkillExtraction]):
    name = "smoke_skill_extraction"
    output_model = SkillExtraction

    def render_prompt(self, inp: str, sources: list[SourceRef]) -> list[Message]:
        return [Message(role="user", content=PROMPT.format(job=inp))]


class ExplodingProvider(LLMProvider):
    """模拟断网。

    刻意沿用真实 Provider 的 name 与 model —— 断网时用户不会去改 .env，
    配置不变、只是网没了。缓存键包含 provider/model，所以身份必须一致，
    否则这个演练就跑偏成「换了模型」而不是「断了网」。
    """

    def __init__(self, name: str, model: str) -> None:
        self.name = name
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def complete(self, messages, **kwargs) -> LLMResponse:  # noqa: ANN001, ANN003
        raise AssertionError("回放模式下不应发起真实调用")


JOB = "AI数据标注工程师"


def main() -> int:
    force_utf8_stdio()
    setup_logging("WARNING")
    create_all()

    print("=" * 66)
    print(f"模型   : {settings.llm_model}")
    print(f"端点   : {settings.llm_base_url}")
    print(f"Key    : {'已配置' if settings.llm_api_key else '缺失'}")
    print("=" * 66)

    if not settings.llm_api_key:
        print("\n❌ 未配置 LLM_API_KEY，请先在 .env 中填入。")
        return 1

    provider = build_provider()

    with session_scope() as db:
        # ---------- 1. 真实调用 ----------
        # 用 LIVE 而非 RECORD：LIVE 语义是「总是真调」，
        # 这样脚本重复运行时这一步也不会退化成缓存命中，验收才有意义。
        print("\n[1/3] 真实调用（LIVE，强制不走缓存）…")
        agent = SkillExtractionAgent(
            runner=LLMRunner(provider=provider, demo_mode=DemoMode.LIVE)
        )
        envelope = agent.run(db, JOB)
        run = db.get(LLMRun, envelope.llm_run_id)
        assert run is not None

        if run.cache_hit:
            print("  ❌ LIVE 模式却命中了缓存，语义有误")
            return 1
        print(f"  ✅ 结构校验通过，抽出 {len(envelope.result.skills)} 项技能")
        print(f"     耗时 {run.latency_ms}ms   tokens in/out = {run.tokens_in}/{run.tokens_out}")
        for skill in envelope.result.skills:
            print(f"       · {skill.name}（{skill.category}）—— {skill.reason}")
        print(f"     置信度 {envelope.confidence}   证据充分性 {envelope.evidence_sufficiency.value}")
        print(f"     提示   {envelope.warnings}")
        print(f"     run_id {envelope.llm_run_id}")

        # ---------- 2. 缓存命中 ----------
        print("\n[2/3] 相同请求再来一次（RECORD 模式，应命中上一步的记录）…")
        recorder = SkillExtractionAgent(
            runner=LLMRunner(provider=provider, demo_mode=DemoMode.RECORD)
        )
        cached = recorder.run(db, JOB)
        cached_run = db.get(LLMRun, cached.llm_run_id)
        assert cached_run is not None

        if not cached_run.cache_hit:
            print("  ❌ 未命中缓存")
            return 1
        print(f"  ✅ 命中缓存，未发起真实调用（耗时 {cached_run.latency_ms}ms，0 token）")
        print(f"     溯源到最初生成：{cached_run.input_summary.get('origin_run_id')}")
        if cached.result.model_dump() != envelope.result.model_dump():
            print("  ❌ 回放结果与原始结果不一致")
            return 1
        print("  ✅ 回放结果与原始结果完全一致")

        # ---------- 3. 断网回放 ----------
        print("\n[3/3] 断网演练：replay 模式 + 一调用就炸的 Provider …")
        offline = SkillExtractionAgent(
            runner=LLMRunner(
                provider=ExplodingProvider(provider.name, provider.model),
                demo_mode=DemoMode.REPLAY,
            )
        )
        replayed = offline.run(db, JOB)
        print(f"  ✅ 断网仍拿到 {len(replayed.result.skills)} 项技能")
        print(f"     提示 {replayed.warnings}")

    print("\n" + "=" * 66)
    print("Phase 2 验收通过：真实调用 / 缓存命中 / 断网回放 三条链路全部跑通")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
