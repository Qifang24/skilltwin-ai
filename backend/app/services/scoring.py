"""能力估计的数学核心。

**这里没有 LLM。** 能力值是统计量，必须由确定性计算得出 ——
这是「LLM 只做生成与解释，不做统计与排序」这条铁律最要紧的落点：
一个学生的能力画像若由模型随口给出，整个自适应学习闭环就没有意义了。

核心问题：3 道题答对 3 道，能力值是 100 吗？

不是。样本量太小，真实水平的不确定性很大。这里用 **Wilson 得分区间**
给出估计区间，而不是把 3/3 直接当成 100 分 ——
「Label Studio: 20 分」这种看似精确实则站不住的数字，比不给数字更有害。

Wilson 区间是小样本比例估计的标准做法，比常见的正态近似
（Wald 区间）在 n 小或比例接近 0/1 时可靠得多 —— 后者在 3/3 时
会给出 [100%, 100%] 这种荒谬结论。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: 95% 置信水平对应的正态分位数
Z_95 = 1.959963984540054

#: 证据充分性的判定阈值。低于此值前端应显示区间而非点估计。
CONFIDENCE_RELIABLE = 0.5

#: 置信度归一化用的区间宽度基准：区间宽度 100 分时置信度为 0
_MAX_WIDTH = 100.0


@dataclass(frozen=True)
class SkillEstimate:
    """单个技能的能力估计。"""

    skill_code: str
    #: 点估计 0~100
    score: float
    score_low: float
    score_high: float
    confidence: float
    #: 加权后的有效题数
    evidence_count: float
    method: str = "wilson"

    @property
    def is_reliable(self) -> bool:
        return self.confidence >= CONFIDENCE_RELIABLE

    @property
    def interval_width(self) -> float:
        return self.score_high - self.score_low


def wilson_interval(
    successes: float, total: float, z: float = Z_95
) -> tuple[float, float, float]:
    """Wilson 得分区间。返回 (中心, 下界, 上界)，均为 0~1 的比例。

    n=0 时返回 (0.5, 0, 1) —— 没有任何证据时，诚实的表述是
    「完全不知道」，而不是 0 分。把「没测过」显示成 0 分会让学生
    以为自己这项能力很差，是实实在在的误导。
    """
    if total <= 0:
        return 0.5, 0.0, 1.0

    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2))
        / denominator
    )
    return centre, max(0.0, centre - margin), min(1.0, centre + margin)


def confidence_from_width(width_pct: float) -> float:
    """由区间宽度导出置信度：区间越窄越可信。

    刻意用区间宽度而不是单纯的题目数量 —— 同样答 4 题，
    全对（4/4）与半对（2/4）的不确定性并不相同，
    前者区间更窄，估计更可信。
    """
    return max(0.0, min(1.0, 1.0 - width_pct / _MAX_WIDTH))


def estimate_skill(
    skill_code: str, weighted_correct: float, weighted_total: float
) -> SkillEstimate:
    """把加权答对数折算成带区间的能力估计。"""
    centre, low, high = wilson_interval(weighted_correct, weighted_total)
    score, score_low, score_high = centre * 100, low * 100, high * 100

    return SkillEstimate(
        skill_code=skill_code,
        score=round(score, 1),
        score_low=round(score_low, 1),
        score_high=round(score_high, 1),
        confidence=round(confidence_from_width(score_high - score_low), 3),
        evidence_count=round(weighted_total, 2),
    )


def aggregate_responses(
    graded: list[tuple[str, float, float]],
) -> dict[str, SkillEstimate]:
    """把逐题得分按技能聚合成能力画像。

    参数 graded 为 [(skill_code, 该题得分 0~1, 该题在此技能上的权重)]。
    同一技能被多题考查时，按权重累加。
    """
    totals: dict[str, list[float]] = {}
    for skill_code, score, weight in graded:
        bucket = totals.setdefault(skill_code, [0.0, 0.0])
        bucket[0] += score * weight
        bucket[1] += weight

    return {
        code: estimate_skill(code, correct, total)
        for code, (correct, total) in totals.items()
    }


# ---------------------------------------------------------------- 差距分析
@dataclass(frozen=True)
class SkillGap:
    skill_code: str
    #: 目标掌握程度换算成的百分制分数
    target_score: float
    current_score: float
    gap: float
    confidence: float
    evidence_count: float
    #: 该差距是否可信 —— 证据不足时不应据此安排学习路径
    reliable: bool

    @property
    def is_met(self) -> bool:
        return self.gap <= 0


#: 掌握程度（1~4）换算成百分制目标分。
#: 不是线性等分：从「了解」到「熟练」的能力要求并非均匀递增，
#: 且入门岗位不要求任何一项达到满分。
MASTERY_TO_SCORE = {1: 40.0, 2: 60.0, 3: 80.0, 4: 90.0}


def compute_gaps(
    target_vector: dict[str, int],
    profile: dict[str, SkillEstimate],
) -> list[SkillGap]:
    """目标能力向量 vs 当前能力画像。

    未测过的技能：current 取 0 但 confidence 也为 0，
    调用方应据此提示「尚未测评」而不是断言「该项能力为零」。
    """
    gaps: list[SkillGap] = []
    for skill_code, mastery in target_vector.items():
        target = MASTERY_TO_SCORE.get(mastery, 60.0)
        estimate = profile.get(skill_code)

        if estimate is None:
            gaps.append(
                SkillGap(
                    skill_code=skill_code,
                    target_score=target,
                    current_score=0.0,
                    gap=target,
                    confidence=0.0,
                    evidence_count=0.0,
                    reliable=False,
                )
            )
            continue

        gaps.append(
            SkillGap(
                skill_code=skill_code,
                target_score=target,
                current_score=estimate.score,
                gap=round(target - estimate.score, 1),
                confidence=estimate.confidence,
                evidence_count=estimate.evidence_count,
                reliable=estimate.is_reliable,
            )
        )

    # 差距大的排前面；同等差距下证据更充分的优先
    return sorted(gaps, key=lambda g: (-g.gap, -g.confidence))
