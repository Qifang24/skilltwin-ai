"""技能归一化测试。

这是全系统头号静默风险的防线：技能名不归一 → join 断裂 →
Gap Analysis 算错且看不出来。
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.enums import SkillCategory, SkillStatus
from app.models.ontology import Skill
from app.services.skill_normalizer import SkillNormalizer, normalize_term


@pytest.fixture
def seeded(db: Session) -> Session:
    db.add_all(
        [
            Skill(
                skill_code="tool.label_studio",
                name_zh="Label Studio",
                name_en="Label Studio",
                category=SkillCategory.TOOL,
                aliases=["LabelStudio", "label-studio", "标注工具Label Studio"],
            ),
            Skill(
                skill_code="data.cleaning",
                name_zh="数据清洗",
                name_en="Data Cleaning",
                category=SkillCategory.DATA,
                aliases=["数据预处理"],
            ),
            Skill(
                skill_code="annot.bbox",
                name_zh="目标检测标注",
                category=SkillCategory.ANNOTATION,
                aliases=["Bounding Box", "矩形框标注"],
                status=SkillStatus.DEPRECATED,
            ),
        ]
    )
    db.commit()
    return db


# ------------------------------------------------------------- normalize_term
def test_normalize_term_collapses_case_and_separators() -> None:
    """这四种写法在真实数据里都出现过，必须压成同一个键。"""
    keys = {
        normalize_term("Label Studio"),
        normalize_term("LabelStudio"),
        normalize_term("label-studio"),
        normalize_term("label_studio"),
    }
    assert len(keys) == 1


def test_normalize_term_folds_fullwidth() -> None:
    """中文输入法下的全角字母必须与半角等价。"""
    assert normalize_term("ＬａｂｅｌＳｔｕｄｉｏ") == normalize_term("LabelStudio")


def test_normalize_term_strips_chinese_punctuation() -> None:
    assert normalize_term("数据、清洗") == normalize_term("数据清洗")


def test_normalize_term_handles_empty() -> None:
    assert normalize_term("") == ""


# ---------------------------------------------------------------- 匹配路径
def test_exact_code_match(seeded: Session) -> None:
    match = SkillNormalizer(seeded).normalize("tool.label_studio")
    assert match.skill_code == "tool.label_studio"
    assert match.matched_by == "exact_code"
    assert match.confidence == 1.0


def test_alias_variants_all_resolve_to_same_code(seeded: Session) -> None:
    """核心场景：同一技能的多种写法必须归到同一个 join key。"""
    normalizer = SkillNormalizer(seeded)
    variants = ["Label Studio", "LabelStudio", "label-studio", "标注工具Label Studio"]
    codes = {normalizer.resolve(v) for v in variants}
    assert codes == {"tool.label_studio"}


def test_chinese_name_matches(seeded: Session) -> None:
    match = SkillNormalizer(seeded).normalize("数据清洗")
    assert match.skill_code == "data.cleaning"
    assert match.matched_by == "exact_alias"


def test_english_name_matches(seeded: Session) -> None:
    assert SkillNormalizer(seeded).resolve("data  cleaning") == "data.cleaning"


def test_unknown_term_is_unmatched_not_guessed(seeded: Session) -> None:
    """刻意不做模糊猜测：宁可交回人工，也不硬塞一个最像的技能。"""
    match = SkillNormalizer(seeded).normalize("量子计算")
    assert match.skill_code is None
    assert match.matched_by == "unmatched"
    assert match.confidence == 0.0


def test_empty_term_is_unmatched(seeded: Session) -> None:
    assert SkillNormalizer(seeded).normalize("   ").matched_by == "unmatched"


# ------------------------------------------------------------ deprecated
def test_deprecated_skill_is_excluded_by_default(seeded: Session) -> None:
    assert SkillNormalizer(seeded).resolve("目标检测标注") is None


def test_deprecated_skill_visible_when_requested(seeded: Session) -> None:
    normalizer = SkillNormalizer(seeded, include_deprecated=True)
    assert normalizer.resolve("目标检测标注") == "annot.bbox"


# ------------------------------------------------------------ 歧义检测
def test_ambiguous_alias_is_reported_not_silently_resolved(db: Session) -> None:
    """两个技能声称同一别名 = join key 有歧义，必须报出来而不是静默择一。"""
    db.add_all(
        [
            Skill(
                skill_code="data.labeling",
                name_zh="数据标注",
                category=SkillCategory.DATA,
                aliases=["标注"],
            ),
            Skill(
                skill_code="annot.text",
                name_zh="文本标注",
                category=SkillCategory.ANNOTATION,
                aliases=["标注"],  # 与上面撞车
            ),
        ]
    )
    db.commit()

    ambiguous = SkillNormalizer(db).ambiguous_aliases
    assert "标注" in ambiguous
    assert set(ambiguous["标注"]) == {"data.labeling", "annot.text"}


def test_normalize_many_counts(seeded: Session) -> None:
    matches = SkillNormalizer(seeded).normalize_many(["数据清洗", "不存在"])
    assert [m.is_matched for m in matches] == [True, False]
