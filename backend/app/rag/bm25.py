"""BM25 稀疏检索（jieba 分词）。

为什么需要它：纯向量检索对**专有技术术语**不可靠。
`Label Studio`、`CVAT`、`COCO`、`mAP`、`YOLO` 这类词在中文语料里出现频次低，
嵌入表示往往不稳，dense 检索容易漏召；而 BM25 靠字面精确匹配，恰好补上这一块。

两者用 RRF 融合，见 retriever.py。
"""

from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

#: 连续的英文/数字串（含点、加号、井号）整体保留，
#: 避免 "label studio" / "yolov8" / "c++" 被切碎后失去检索价值
_ASCII_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#._-]*|\d+(?:\.\d+)?")

#: 中文停用词，只列高频虚词；宁可少删，避免误伤专业术语
_STOPWORDS = {
    "的", "了", "和", "与", "及", "或", "在", "是", "为", "对", "等", "中",
    "上", "下", "并", "以", "被", "把", "从", "到", "由", "该", "本", "其",
    "a", "an", "the", "of", "and", "or", "to", "in", "for", "with",
}


def tokenize(text: str) -> list[str]:
    """中英混合分词。

    英文/数字串整体保留后再走 jieba，避免技术术语被拆散。
    """
    if not text:
        return []

    import jieba

    tokens: list[str] = []
    cursor = 0
    for match in _ASCII_TOKEN.finditer(text):
        chinese_part = text[cursor : match.start()]
        if chinese_part:
            tokens.extend(jieba.lcut(chinese_part))
        tokens.append(match.group())
        cursor = match.end()
    if cursor < len(text):
        tokens.extend(jieba.lcut(text[cursor:]))

    return [
        token
        for raw in tokens
        if (token := raw.strip().lower()) and token not in _STOPWORDS and len(token) > 0
    ]


@dataclass
class SparseHit:
    chunk_id: str
    score: float


class BM25Index:
    """可持久化的 BM25 索引。"""

    def __init__(self) -> None:
        self._chunk_ids: list[str] = []
        self._bm25 = None

    @property
    def size(self) -> int:
        return len(self._chunk_ids)

    def build(self, chunk_ids: list[str], texts: list[str]) -> None:
        from rank_bm25 import BM25Okapi

        if not chunk_ids:
            self._chunk_ids, self._bm25 = [], None
            return

        corpus = [tokenize(t) for t in texts]
        # 全空文档会让 BM25Okapi 计算平均长度时除零
        corpus = [tokens or ["__empty__"] for tokens in corpus]

        self._chunk_ids = list(chunk_ids)
        self._bm25 = BM25Okapi(corpus)
        logger.info("BM25 索引构建完成", extra={"documents": len(corpus)})

    def search(self, query: str, top_k: int) -> list[SparseHit]:
        if self._bm25 is None or not self._chunk_ids:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            zip(self._chunk_ids, scores), key=lambda pair: pair[1], reverse=True
        )
        # 过滤零分：BM25 会给全部文档打分，零分说明一个查询词都没命中
        return [
            SparseHit(chunk_id=cid, score=float(score))
            for cid, score in ranked[:top_k]
            if score > 0
        ]

    # ------------------------------------------------------------------ 持久化
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump({"chunk_ids": self._chunk_ids, "bm25": self._bm25}, handle)

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        index = cls()
        if not path.exists():
            return index
        try:
            with path.open("rb") as handle:
                payload = pickle.load(handle)
            index._chunk_ids = payload["chunk_ids"]
            index._bm25 = payload["bm25"]
        except Exception as exc:  # pragma: no cover - 索引损坏时退化为空索引
            logger.warning("BM25 索引加载失败，将退化为纯向量检索", extra={"error": str(exc)})
        return index
