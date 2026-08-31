"""应用配置。

所有可变配置集中在此，通过环境变量 / .env 注入。
铁律：任何 API Key 只能从环境读取，禁止出现在代码或数据库中。
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .../backend/app/core/config.py -> challenge_cup/
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DemoMode(str, Enum):
    """LLM 调用模式。

    live   —— 正常调用远端模型
    record —— 正常调用，同时把结果写入 llm_run 供日后回放
    replay —— 只从 llm_run 缓存回放，不发起网络请求（断网演示用）
    """

    LIVE = "live"
    RECORD = "record"
    REPLAY = "replay"


class LLMProviderName(str, Enum):
    OPENAI_COMPAT = "openai_compat"  # DeepSeek / Qwen / OpenRouter / SiliconFlow
    SPARK = "spark"  # 科大讯飞星火 HTTP OpenAI-compatible API
    XINGCHEN_WORKFLOW = "xingchen_workflow"  # 科大讯飞星辰 Agent Workflow OpenAPI
    ECHO = "echo"  # 测试用，不发网络请求


class EmbeddingProviderName(str, Enum):
    LOCAL_BGE = "local_bge"  # sentence-transformers，本地 CUDA，无需 key
    OPENAI_COMPAT = "openai_compat"  # 如 Qwen text-embedding-v3
    HASH = "hash"  # 仅测试：确定性伪向量，绝不可用于生产


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )

    # ---------- 应用 ----------
    app_name: str = "SkillTwin AI"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # ---------- 路径 ----------
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    knowledge_dir: Path = PROJECT_ROOT / "knowledge"
    seed_dir: Path = PROJECT_ROOT / "data" / "seed"
    chroma_dir: Path = PROJECT_ROOT / "data" / "chroma"

    # ---------- 数据库 ----------
    database_url: str = ""  # 空则由 data_dir 推导，见 validator

    # ---------- LLM ----------
    demo_mode: DemoMode = DemoMode.LIVE
    llm_provider: LLMProviderName = LLMProviderName.OPENAI_COMPAT
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    # 兼容项目既有 LLM_API_KEY，也可安全复用标准 OPENAI_API_KEY。
    llm_api_key: str = Field(default="", validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"))
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.2

    # ---------- 科大讯飞星火 HTTP API ----------
    # 官方 HTTP/OpenAI-compatible 接口使用控制台的 APIPassword，
    # 不要与 WebSocket 的 APIKey/APISecret 混用。
    spark_base_url: str = "https://spark-api-open.xf-yun.com/v1"
    spark_model: str = "4.0Ultra"
    spark_api_password: str = ""

    # 保留 WebSocket 凭证配置名，方便已有部署迁移；本项目的 SparkProvider
    # 使用 HTTP APIPassword，不会读取这三个字段。
    spark_app_id: str = ""
    spark_api_key: str = ""
    spark_api_secret: str = ""

    # ---------- 科大讯飞星辰 Agent Workflow OpenAPI ----------
    xingchen_base_url: str = "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions"
    xingchen_flow_id: str = ""
    xingchen_api_key: str = ""
    xingchen_api_secret: str = ""
    xingchen_input_parameter: str = "AGENT_USER_INPUT"
    xingchen_uid: str = ""

    # ---------- Embedding ----------
    embedding_provider: EmbeddingProviderName = EmbeddingProviderName.LOCAL_BGE
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_device: str = "auto"  # auto | cuda | cpu
    embedding_dim: int = 512  # bge-small-zh-v1.5 输出维度
    embedding_batch_size: int = 32

    # ---------- RAG ----------
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieve_dense_top_k: int = 20
    retrieve_sparse_top_k: int = 20
    retrieve_final_top_n: int = 8
    rrf_k: int = 60  # Reciprocal Rank Fusion 常数

    @field_validator("database_url", mode="after")
    @classmethod
    def _default_sqlite_url(cls, v: str) -> str:
        if v:
            return v
        db_path = PROJECT_ROOT / "data" / "skilltwin.db"
        # SQLAlchemy 的 sqlite URL 在 Windows 上需要正斜杠
        return f"sqlite:///{db_path.as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_dirs(self) -> None:
        """启动时保证运行期目录存在（这些目录不进 git）。"""
        for d in (self.data_dir, self.seed_dir, self.chroma_dir, self.knowledge_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
