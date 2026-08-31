"""技能相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import Provenance, SkillCategory, SkillStatus

#: skill_code 前缀 ↔ 技能大类。前缀必须与 category 一致，
#: 由 ExtractedSkill 的校验器强制，避免出现 tool.* 却归到 data 类这种自相矛盾。
CATEGORY_PREFIX: dict[SkillCategory, str] = {
    SkillCategory.PROGRAMMING: "prog",
    SkillCategory.DATA: "data",
    SkillCategory.ANNOTATION: "annot",
    SkillCategory.TOOL: "tool",
    SkillCategory.AI_THEORY: "ai",
    SkillCategory.QUALITY: "quality",
    SkillCategory.SOFT: "soft",
}
PREFIX_CATEGORY: dict[str, SkillCategory] = {v: k for k, v in CATEGORY_PREFIX.items()}


class ExtractedSkill(BaseModel):
    """从标准原文中抽取出的候选技能。"""

    skill_code: str = Field(pattern=r"^[a-z]+\.[a-z0-9_]+$", max_length=96)
    name_zh: str = Field(min_length=2, max_length=64)
    name_en: str | None = Field(default=None, max_length=64)
    category: SkillCategory
    description: str = Field(min_length=4, max_length=400)
    aliases: list[str] = Field(default_factory=list, max_length=12)

    #: **必须是来源 chunk 原文的精确子串**。这是防编造的机械闸门：
    #: 校验对不上的候选一律丢弃，模型无法凭空造出一条「依据」。
    evidence_quote: str = Field(min_length=4, max_length=300)

    @field_validator("skill_code")
    @classmethod
    def _prefix_must_be_known(cls, v: str) -> str:
        prefix = v.split(".", 1)[0]
        if prefix not in PREFIX_CATEGORY:
            raise ValueError(
                f"未知的 skill_code 前缀 '{prefix}'，"
                f"可用前缀：{sorted(PREFIX_CATEGORY)}"
            )
        return v

    def prefix_matches_category(self) -> bool:
        return self.skill_code.split(".", 1)[0] == CATEGORY_PREFIX[self.category]


class SkillExtractionResult(BaseModel):
    """一个 chunk 的抽取结果。"""

    skills: list[ExtractedSkill] = Field(default_factory=list, max_length=15)


class SkillSourceRef(BaseModel):
    """技能的出处，支撑「这个技能点凭什么存在」的下钻。"""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    doc_id: str | None = None
    source_name: str | None = None
    standard_id: str | None = None
    page: str | None = None
    section: str | None = None
    quote: str


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_code: str
    name_zh: str
    name_en: str | None = None
    category: SkillCategory
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    status: SkillStatus
    provenance: Provenance


class SkillDetail(SkillRead):
    """详情视图，附带来源引用。"""

    sources: list[SkillSourceRef] = Field(default_factory=list)


class NormalizeRequest(BaseModel):
    terms: list[str] = Field(min_length=1, max_length=200)


class NormalizeMatch(BaseModel):
    """一个词条的归一化结果。

    matched_by 说明是怎么匹配上的，便于排查「为什么这个词归到了那个技能」：
        exact_code / exact_alias / unmatched
        （embedding / llm 待 Phase 4 接入）
    """

    term: str
    skill_code: str | None = None
    name_zh: str | None = None
    matched_by: str
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def is_matched(self) -> bool:
        return self.skill_code is not None


class NormalizeResponse(BaseModel):
    matches: list[NormalizeMatch]
    matched_count: int
    unmatched_count: int
