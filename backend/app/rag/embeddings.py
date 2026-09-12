"""Embedding Provider 抽象。

默认走**本地** `BAAI/bge-small-zh-v1.5`：中文检索效果好、约 95MB、
可用 GPU，且**不需要 API Key、不产生费用、可完全离线**。
这一点对本项目很关键 —— DeepSeek 没有 embedding 接口，
若把向量化也绑到 API 上，断网演示就不成立了。

所有实现统一返回 L2 归一化后的向量，因此余弦相似度 = 内积。
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np

from app.core.config import EmbeddingProviderName, settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: bge 系列建议给「短查询检索长文档」的查询加指令前缀，可提升召回。
#: 文档侧不加。
BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    # 零向量保持为零，避免除零产生 nan 污染整个索引
    norms[norms == 0] = 1.0
    return matrix / norms


class EmbeddingProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        """返回 (len(texts), dim) 的 L2 归一化向量。"""

    def embed_one(self, text: str, *, is_query: bool = False) -> np.ndarray:
        return self.embed([text], is_query=is_query)[0]


class LocalBGEProvider(EmbeddingProvider):
    """本地 sentence-transformers。首次使用会下载模型（约 95MB）。"""

    name = "local_bge"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        *,
        use_query_instruction: bool = True,
    ) -> None:
        self._model_name = model_name or settings.embedding_model
        self._device_pref = device or settings.embedding_device
        self._use_instruction = use_query_instruction
        self._model = None  # 延迟加载：健康检查等场景不该为此付出数秒与显存

    def _resolve_device(self) -> str:
        if self._device_pref in ("cuda", "cpu"):
            return self._device_pref
        try:
            import torch

            if not torch.cuda.is_available():
                return "cpu"

            # 新显卡可能被旧版 PyTorch 识别到，却没有对应的 CUDA kernel。
            # 此时让 sentence-transformers 使用 CUDA 会在首次检索才失败；预先
            # 回退到 CPU，保证图谱生成仍可使用向量检索。
            capability = torch.cuda.get_device_capability(0)
            device_arch = f"sm_{capability[0]}{capability[1]}"
            supported_arches = set(torch.cuda.get_arch_list())
            if device_arch not in supported_arches:
                logger.warning(
                    "当前 PyTorch 不支持该 CUDA 架构，embedding 将使用 CPU",
                    extra={"device_arch": device_arch, "supported_arches": sorted(supported_arches)},
                )
                return "cpu"
            return "cuda"
        except Exception:  # pragma: no cover - 取决于运行环境
            return "cpu"

    @property
    def model(self):  # noqa: ANN201
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            device = self._resolve_device()
            logger.info(
                "加载本地 embedding 模型",
                extra={"model": self._model_name, "device": device},
            )
            self._model = SentenceTransformer(self._model_name, device=device)
        return self._model

    @property
    def dim(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)

        prepared = texts
        if is_query and self._use_instruction:
            prepared = [BGE_QUERY_INSTRUCTION + t for t in texts]

        vectors = self.model.encode(
            prepared,
            batch_size=settings.embedding_batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


class OpenAICompatEmbeddingProvider(EmbeddingProvider):
    """走 API 的 embedding（如通义 text-embedding-v3）。

    注意：DeepSeek **没有** embedding 接口，配这个的话 base_url/model
    必须指向确实提供该能力的服务。
    """

    name = "openai_compat"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._base_url = base_url if base_url is not None else settings.llm_base_url
        self._model = model or settings.embedding_model
        self._dim = dim or settings.embedding_dim
        self._client = None

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        if self._client is None:
            if not self._api_key:
                raise ConfigurationError("使用 API embedding 需要配置 LLM_API_KEY")
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)

        response = self._client.embeddings.create(model=self._model, input=texts)
        vectors = np.asarray(
            [item.embedding for item in response.data], dtype=np.float32
        )
        return l2_normalize(vectors)


class HashEmbeddingProvider(EmbeddingProvider):
    """确定性伪向量，**仅供测试**，绝不可用于生产检索。

    把字符 n-gram 哈希到固定维度，因此字面重合的文本会得到较高相似度 ——
    足以让检索链路的单元测试断言排序，又不必加载真实模型（省数秒与显存）。
    它**不具备语义理解**：近义词不会相似。
    """

    name = "hash"

    def __init__(self, dim: int = 256, ngram: int = 2) -> None:
        self._dim = dim
        self._ngram = ngram

    @property
    def dim(self) -> int:
        return self._dim

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self._dim, dtype=np.float32)
        cleaned = "".join(text.split())
        if not cleaned:
            return vector
        grams = [
            cleaned[i : i + self._ngram]
            for i in range(max(len(cleaned) - self._ngram + 1, 1))
        ]
        for gram in grams:
            digest = hashlib.md5(gram.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "little") % self._dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return vector

    def embed(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        return l2_normalize(np.vstack([self._vector(t) for t in texts]))


def build_embedding_provider(
    name: EmbeddingProviderName | None = None,
) -> EmbeddingProvider:
    provider = name or settings.embedding_provider
    if provider is EmbeddingProviderName.LOCAL_BGE:
        return LocalBGEProvider()
    if provider is EmbeddingProviderName.OPENAI_COMPAT:
        return OpenAICompatEmbeddingProvider()
    if provider is EmbeddingProviderName.HASH:
        logger.warning("正在使用 hash 伪向量，仅适用于测试，不具备语义检索能力")
        return HashEmbeddingProvider()
    raise ConfigurationError(f"未知的 EMBEDDING_PROVIDER：{provider}")


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """进程内单例 —— 模型加载代价高，不能每次请求都来一遍。"""
    return build_embedding_provider()
