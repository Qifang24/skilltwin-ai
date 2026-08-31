"""能力估计数学核心的测试。

这里守的是本项目最容易出「假精度」的地方：
少量题目算不出精确能力值，系统必须诚实地表达不确定性。
"""

from __future__ import annotations

import pytest

from app.services.scoring import (
    MASTERY_TO_SCORE,
    SkillEstimate,
    aggregate_responses,
    compute_gaps,
    confidence_from_width,
    estimate_skill,
    wilson_interval,
)


# ---------------------------------------------------------------- Wilson
def test_no_evidence_means_unknown_not_zero() -> None:
    """没测过 ≠ 能力为零。

    把「没测过」显示成 0 分会让学生以为自己这项很差，是实实在在的误导。
    """
    centre, low, high = wilson_interval(0, 0)
    assert centre == 0.5
    assert (low, high) == (0.0, 1.0)  # 完全不确定


def test_perfect_small_sample_is_not_100_percent() -> None:
    """3 题全对不等于能力 100。

    这是本项目最容易犯的假精度错误。Wald 区间在此会给出 [100%,100%]，
    Wilson 不会。
    """
    centre, low, high = wilson_interval(3, 3)
    assert centre < 1.0, "3/3 的点估计不应是 100%"
    assert low < 0.6, "样本太小，下界应当很低"
    assert high == pytest.approx(1.0, abs=0.01)


def test_interval_narrows_as_evidence_grows() -> None:
    """证据越多，区间越窄 —— 这是置信度的来源。"""
    _, low_3, high_3 = wilson_interval(3, 3)
    _, low_30, high_30 = wilson_interval(30, 30)
    assert (high_30 - low_30) < (high_3 - low_3)


def test_half_correct_centres_near_half() -> None:
    centre, low, high = wilson_interval(10, 20)
    assert centre == pytest.approx(0.5, abs=0.02)
    assert low < 0.5 < high


def test_zero_correct_is_not_certainly_zero() -> None:
    """0/3 也不该断言能力为 0，上界应留有余地。"""
    centre, low, high = wilson_interval(0, 3)
    assert low == pytest.approx(0.0, abs=1e-9)  # 浮点余项，实际就是 0
    assert high > 0.3, "样本太小，不能断定完全不会"


# ------------------------------------------------------------ 置信度
def test_confidence_reflects_interval_width() -> None:
    assert confidence_from_width(0) == 1.0
    assert confidence_from_width(100) == 0.0
    assert confidence_from_width(50) == pytest.approx(0.5)


def test_same_item_count_different_confidence() -> None:
    """同样 4 题，全对比半对的估计更可信 —— 所以用区间宽度而非题数。"""
    all_correct = estimate_skill("s", 4, 4)
    half_correct = estimate_skill("s", 2, 4)
    assert all_correct.confidence > half_correct.confidence


# ------------------------------------------------------------ 能力估计
def test_estimate_carries_interval_and_evidence() -> None:
    est = estimate_skill("annot.image", 3, 4)
    assert est.score_low < est.score < est.score_high
    assert est.evidence_count == 4
    assert est.method == "wilson"


def test_small_sample_is_flagged_unreliable() -> None:
    """1 题的估计不该被当作可信结论展示。"""
    assert estimate_skill("s", 1, 1).is_reliable is False


def test_large_sample_becomes_reliable() -> None:
    assert estimate_skill("s", 18, 20).is_reliable is True


# ------------------------------------------------------------ 聚合
def test_aggregate_groups_by_skill() -> None:
    profile = aggregate_responses(
        [
            ("annot.image", 1.0, 1.0),
            ("annot.image", 0.0, 1.0),
            ("data.cleaning", 1.0, 1.0),
        ]
    )
    assert set(profile) == {"annot.image", "data.cleaning"}
    assert profile["annot.image"].evidence_count == 2
    assert profile["data.cleaning"].evidence_count == 1


def test_aggregate_respects_weights() -> None:
    """一道题可以主要考查某技能、附带考查另一技能。"""
    profile = aggregate_responses(
        [("annot.image", 1.0, 1.0), ("quality.audit", 1.0, 0.3)]
    )
    assert profile["quality.audit"].evidence_count == pytest.approx(0.3)
    # 证据更少 → 区间更宽 → 置信度更低
    assert profile["quality.audit"].confidence < profile["annot.image"].confidence


def test_aggregate_empty_returns_empty() -> None:
    assert aggregate_responses([]) == {}


# ------------------------------------------------------------ Gap
def test_gap_uses_mastery_mapping() -> None:
    gaps = compute_gaps({"annot.image": 3}, {"annot.image": estimate_skill("annot.image", 8, 10)})
    gap = gaps[0]
    assert gap.target_score == MASTERY_TO_SCORE[3]
    assert gap.gap == pytest.approx(gap.target_score - gap.current_score, abs=0.1)


def test_untested_skill_is_marked_unreliable() -> None:
    """未测评的技能：差距按满额算，但必须标为不可信。

    否则学习路径会把「没测过」当成「很差」来安排，浪费学生时间。
    """
    gaps = compute_gaps({"tool.label_studio": 3}, {})
    gap = gaps[0]
    assert gap.current_score == 0.0
    assert gap.confidence == 0.0
    assert gap.reliable is False
    assert gap.evidence_count == 0


def test_gaps_sorted_by_size_then_confidence() -> None:
    profile = {
        "a": estimate_skill("a", 9, 10),  # 高分 → 差距小
        "b": estimate_skill("b", 2, 10),  # 低分 → 差距大
    }
    gaps = compute_gaps({"a": 3, "b": 3}, profile)
    assert [g.skill_code for g in gaps] == ["b", "a"]


def test_met_target_has_non_positive_gap() -> None:
    gaps = compute_gaps({"a": 1}, {"a": estimate_skill("a", 20, 20)})
    assert gaps[0].is_met is True


def test_estimate_is_immutable() -> None:
    """能力估计一旦算出不应被就地改动 —— 画像是快照。"""
    est = SkillEstimate("s", 50, 30, 70, 0.6, 5)
    with pytest.raises(Exception):
        est.score = 99  # type: ignore[misc]
