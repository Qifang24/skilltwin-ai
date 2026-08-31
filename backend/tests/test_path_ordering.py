"""学习路径排序算法测试。

守的是架构铁律：顺序必须是**算出来的**，不是模型排的。
因此这里的每条断言都在确认「为什么 A 排在 B 前面」有确定性依据。
"""

from __future__ import annotations

from app.services.path_ordering import (
    find_cycles,
    merge_small_layers,
    order_by_prerequisites,
)
from app.services.scoring import SkillGap


def gap(code: str, size: float, confidence: float = 0.8) -> SkillGap:
    return SkillGap(
        skill_code=code,
        target_score=80.0,
        current_score=80.0 - size,
        gap=size,
        confidence=confidence,
        evidence_count=10.0,
        reliable=confidence >= 0.5,
    )


# ---------------------------------------------------------------- 无依赖
def test_no_prereq_orders_by_gap_desc() -> None:
    result = order_by_prerequisites(
        [gap("a", 10), gap("b", 40), gap("c", 25)], prereq_edges=[]
    )
    assert len(result.layers) == 1
    assert [g.skill_code for g in result.layers[0].gaps] == ["b", "c", "a"]


def test_ties_broken_by_confidence() -> None:
    """差距相同时，证据充分的优先 —— 有把握的结论先安排。"""
    result = order_by_prerequisites(
        [gap("low", 30, confidence=0.3), gap("high", 30, confidence=0.9)],
        prereq_edges=[],
    )
    assert [g.skill_code for g in result.layers[0].gaps] == ["high", "low"]


def test_empty_input_yields_no_layers() -> None:
    assert order_by_prerequisites([], []).layers == []


# ---------------------------------------------------------------- 拓扑
def test_prerequisite_comes_first_even_with_smaller_gap() -> None:
    """核心断言：前置依赖优先于差距大小。

    基础技能差距小，但必须先学 —— 这正是需要拓扑排序而非单纯排差距的原因。
    """
    result = order_by_prerequisites(
        [gap("basic", 5), gap("advanced", 50)],
        prereq_edges=[("basic", "advanced")],
    )
    assert [g.skill_code for g in result.layers[0].gaps] == ["basic"]
    assert [g.skill_code for g in result.layers[1].gaps] == ["advanced"]


def test_chain_produces_three_layers() -> None:
    result = order_by_prerequisites(
        [gap("a", 10), gap("b", 20), gap("c", 30)],
        prereq_edges=[("a", "b"), ("b", "c")],
    )
    assert [[g.skill_code for g in layer.gaps] for layer in result.layers] == [
        ["a"],
        ["b"],
        ["c"],
    ]


def test_parallel_skills_share_a_layer() -> None:
    """互不依赖的技能应放同一阶段，可并行学，不必人为串起来。"""
    result = order_by_prerequisites(
        [gap("root", 10), gap("x", 30), gap("y", 20)],
        prereq_edges=[("root", "x"), ("root", "y")],
    )
    assert [g.skill_code for g in result.layers[1].gaps] == ["x", "y"]


def test_edges_outside_scope_are_ignored() -> None:
    """指向本次学习范围外技能的依赖，不应约束排序。"""
    result = order_by_prerequisites(
        [gap("a", 10)], prereq_edges=[("not_in_scope", "a")]
    )
    assert len(result.layers) == 1
    assert result.warnings == []


def test_self_loop_is_ignored() -> None:
    result = order_by_prerequisites([gap("a", 10)], prereq_edges=[("a", "a")])
    assert len(result.layers) == 1


# ---------------------------------------------------------------- 环
def test_find_cycles_detects_simple_cycle() -> None:
    cycles = find_cycles([("a", "b"), ("b", "a")], {"a", "b"})
    assert cycles
    assert set(cycles[0]) == {"a", "b"}


def test_find_cycles_returns_empty_for_dag() -> None:
    assert find_cycles([("a", "b"), ("b", "c")], {"a", "b", "c"}) == []


def test_cycle_is_reported_not_silently_resolved() -> None:
    """成环时不能悄悄挑一个顺序 —— 那是把无解问题伪装成有解。"""
    result = order_by_prerequisites(
        [gap("a", 10), gap("b", 20)], prereq_edges=[("a", "b"), ("b", "a")]
    )
    assert any("循环" in w for w in result.warnings)
    # 成环技能仍要出现在结果里，不能凭空消失
    placed = {g.skill_code for layer in result.layers for g in layer.gaps}
    assert placed == {"a", "b"}


def test_cycle_does_not_lose_unrelated_skills() -> None:
    result = order_by_prerequisites(
        [gap("a", 10), gap("b", 20), gap("solo", 30)],
        prereq_edges=[("a", "b"), ("b", "a")],
    )
    placed = {g.skill_code for layer in result.layers for g in layer.gaps}
    assert placed == {"a", "b", "solo"}


# ---------------------------------------------------------------- 合并
def test_merge_reduces_phase_count() -> None:
    gaps = [gap(f"s{i}", 10 + i) for i in range(8)]
    edges = [(f"s{i}", f"s{i + 1}") for i in range(7)]  # 8 层链
    result = order_by_prerequisites(gaps, edges)
    assert len(result.layers) == 8

    merged = merge_small_layers(result, max_phases=4)
    assert len(merged.layers) <= 4


def test_merge_preserves_prerequisite_order() -> None:
    """合并只能并相邻层，绝不能把后继排到前置之前。"""
    gaps = [gap(f"s{i}", 10) for i in range(6)]
    edges = [(f"s{i}", f"s{i + 1}") for i in range(5)]
    merged = merge_small_layers(order_by_prerequisites(gaps, edges), max_phases=3)

    position = {}
    for phase_index, layer in enumerate(merged.layers):
        for g in layer.gaps:
            position[g.skill_code] = phase_index

    for prereq, target in edges:
        assert position[prereq] <= position[target], (
            f"{prereq} 是 {target} 的前置，却被排到了后面"
        )


def test_merge_keeps_all_skills() -> None:
    gaps = [gap(f"s{i}", 10) for i in range(9)]
    edges = [(f"s{i}", f"s{i + 1}") for i in range(8)]
    merged = merge_small_layers(order_by_prerequisites(gaps, edges), max_phases=3)
    placed = {g.skill_code for layer in merged.layers for g in layer.gaps}
    assert len(placed) == 9


def test_merge_noop_when_already_few_layers() -> None:
    result = order_by_prerequisites([gap("a", 10), gap("b", 20)], [])
    assert merge_small_layers(result, max_phases=4) is result
