"""技能归一化 —— 全系统 join key 的守门人。

任何位置出现的技能名（岗位 JD 抽取、课程产出、实训任务、测评题、学生画像）
都必须先经这里归一到规范 `skill_code`，否则
`Label Studio` / `LabelStudio` / `标注工具Label Studio` 会变成三个维度，
Gap Analysis 会**静默算错** —— 错得看不出来，比崩溃更危险。

匹配顺序**不可颠倒**，确定性手段优先、代价最低者优先：

    1. 精确匹配 skill_code
    2. 归一化后精确匹配 名称 / 别名
    3. (Phase 4) embedding 近邻，需超过阈值
    4. (Phase 4) LLM 兜底
    5. 全部未命中 → unmatched，**绝不猜**

第 5 步是刻意的：宁可交回一个「没匹配上」让人来看，
也不要硬塞给一个最像的技能 —— 后者会污染整张能力表且无从察觉。
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import SkillStatus
from app.core.logging import get_logger
from app.models.ontology import Skill
from app.schemas.skill import NormalizeMatch

logger = get_logger(__name__)

#: 归一化时剥离的字符：空白、连字符、下划线、点、斜杠及常见中英标点
_STRIP_CHARS = re.compile(r"[\s\-_./\\·、，,。;；:：()（）\[\]【】「」《》\"'`]+")


def normalize_term(term: str) -> str:
    """把一个技能写法压成比对用的规范形式。

    全角→半角、转小写、去除所有分隔符与标点。
    于是 "Label Studio" / "label-studio" / "ＬａｂｅｌＳｔｕｄｉｏ"
    都归到同一个键 "labelstudio"。
    """
    if not term:
        return ""
    # NFKC 把全角字符与兼容字符折叠到标准形式
    folded = unicodedata.normalize("NFKC", term).casefold()
    return _STRIP_CHARS.sub("", folded)


class SkillNormalizer:
    """把任意技能写法解析为规范 skill_code。

    索引在实例化时一次性构建，避免逐条查库。
    技能表变动后需重建实例（或调用 refresh）。
    """

    def __init__(self, db: Session, *, include_deprecated: bool = False) -> None:
        self._db = db
        self._include_deprecated = include_deprecated
        self._by_code: dict[str, Skill] = {}
        self._by_normalized: dict[str, Skill] = {}
        #: 归一化后撞车的写法：多个技能声称同一个别名，属数据问题，需人工消歧
        self._ambiguous: dict[str, list[str]] = {}
        self.refresh()

    def refresh(self) -> None:
        stmt = select(Skill)
        if not self._include_deprecated:
            stmt = stmt.where(Skill.status == SkillStatus.ACTIVE)
        skills = self._db.execute(stmt).scalars().all()

        self._by_code = {s.skill_code: s for s in skills}
        self._by_normalized = {}
        self._ambiguous = {}

        for skill in skills:
            for raw in (skill.skill_code, skill.name_zh, skill.name_en, *skill.aliases):
                if not raw:
                    continue
                key = normalize_term(raw)
                if not key:
                    continue
                existing = self._by_normalized.get(key)
                if existing is None:
                    self._by_normalized[key] = skill
                elif existing.skill_code != skill.skill_code:
                    # 别名撞车：不静默择一，记录下来供排查
                    self._ambiguous.setdefault(key, [existing.skill_code]).append(
                        skill.skill_code
                    )

        if self._ambiguous:
            logger.warning(
                "存在归一化后重复的技能别名，需人工消歧",
                extra={"ambiguous": {k: v for k, v in list(self._ambiguous.items())[:10]}},
            )

    @property
    def size(self) -> int:
        return len(self._by_code)

    @property
    def ambiguous_aliases(self) -> dict[str, list[str]]:
        """归一化后撞车的别名。应当为空；不为空说明技能表需要清理。"""
        return dict(self._ambiguous)

    def normalize(self, term: str) -> NormalizeMatch:
        raw = (term or "").strip()
        if not raw:
            return NormalizeMatch(term=term, matched_by="unmatched", confidence=0.0)

        # ---- 1. 精确匹配 skill_code ----
        if raw in self._by_code:
            skill = self._by_code[raw]
            return NormalizeMatch(
                term=term,
                skill_code=skill.skill_code,
                name_zh=skill.name_zh,
                matched_by="exact_code",
                confidence=1.0,
            )

        # ---- 2. 归一化后匹配名称 / 别名 ----
        key = normalize_term(raw)
        skill = self._by_normalized.get(key)
        if skill is not None:
            return NormalizeMatch(
                term=term,
                skill_code=skill.skill_code,
                name_zh=skill.name_zh,
                matched_by="exact_alias",
                confidence=0.95,
            )

        # ---- 3/4. embedding 近邻与 LLM 兜底：Phase 4 接入 ----
        # 届时在此按阈值召回，低于阈值仍应落到 unmatched，不得强行归类。

        # ---- 5. 未命中：如实交回 ----
        return NormalizeMatch(term=term, matched_by="unmatched", confidence=0.0)

    def normalize_many(self, terms: list[str]) -> list[NormalizeMatch]:
        return [self.normalize(t) for t in terms]

    def resolve(self, term: str) -> str | None:
        """便捷方法：只要 skill_code，未命中返回 None。"""
        return self.normalize(term).skill_code
