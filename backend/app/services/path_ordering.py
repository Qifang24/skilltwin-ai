"""学习路径排序的确定性算法。

**这里没有 LLM。** 「先学 A 再学 B」必须是有依据的推导，
而不是模型觉得应该这样 —— 这是「LLM 不做排序」这条铁律的落点。

算法：
  1. 按前置依赖做**拓扑分层**（Kahn 算法）。同一层的技能互不依赖，可并行学。
  2. 层内按**能力差距降序**排 —— 差距大的先补。
  3. 差距相同的按证据充分度降序 —— 有把握的结论优先。

对环的处理是要害：前置关系一旦成环（A 需要 B、B 需要 A），
拓扑排序无解。此时**不能悄悄挑一个顺序**，而要如实报告环的位置，
把成环的技能放在同一层（视为需要一起学），并给出警告。
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.services.scoring import SkillGap


@dataclass
class OrderedLayer:
    """拓扑分层结果的一层。"""

    index: int
    #: 该层的技能，已按差距降序排好
    gaps: list[SkillGap]
    #: 该层被排在此处的依据说明
    note: str = ""


@dataclass
class OrderingResult:
    layers: list[OrderedLayer] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    method: str = "topological+gap_desc"

    @property
    def total_skills(self) -> int:
        return sum(len(layer.gaps) for layer in self.layers)


def find_cycles(edges: list[tuple[str, str]], nodes: set[str]) -> list[list[str]]:
    """找出前置关系中的环。用于如实报告，而不是掩盖。

    edges 为 (前置, 后继) 对。
    """
    successors: dict[str, list[str]] = defaultdict(list)
    for prereq, target in edges:
        successors[prereq].append(target)

    cycles: list[list[str]] = []
    state: dict[str, int] = {}  # 0 未访问 1 在栈中 2 已完成
    stack: list[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in successors.get(node, []):
            if state.get(nxt, 0) == 0:
                visit(nxt)
            elif state.get(nxt) == 1:
                # 回边 → 找到环
                start = stack.index(nxt)
                cycles.append([*stack[start:], nxt])
        stack.pop()
        state[node] = 2

    for node in sorted(nodes):
        if state.get(node, 0) == 0:
            visit(node)
    return cycles


def order_by_prerequisites(
    gaps: list[SkillGap],
    prereq_edges: list[tuple[str, str]],
) -> OrderingResult:
    """把待补技能排成有先后的学习层次。

    gaps        待补的技能差距（应已过滤掉已达标项）
    prereq_edges (前置技能, 后继技能) 对
    """
    result = OrderingResult()
    if not gaps:
        return result

    by_code = {gap.skill_code: gap for gap in gaps}
    nodes = set(by_code)

    # 只保留两端都在本次学习范围内的依赖 ——
    # 指向范围外技能的依赖无法约束本次排序
    edges = [
        (prereq, target)
        for prereq, target in prereq_edges
        if prereq in nodes and target in nodes and prereq != target
    ]

    cycles = find_cycles(edges, nodes)
    cycle_nodes: set[str] = set()
    if cycles:
        for cycle in cycles:
            cycle_nodes.update(cycle)
        shown = " → ".join(cycles[0])
        result.warnings.append(
            f"前置依赖中存在循环（如 {shown}），无法确定先后顺序。"
            f"涉及的 {len(cycle_nodes)} 项技能已并入同一阶段，建议教师检查依赖设置。"
        )
        # 去掉成环的边，剩余部分仍可正常分层
        edges = [
            (a, b) for a, b in edges if a not in cycle_nodes or b not in cycle_nodes
        ]

    # ---- Kahn 分层 ----
    indegree: dict[str, int] = {code: 0 for code in nodes}
    successors: dict[str, list[str]] = defaultdict(list)
    for prereq, target in edges:
        successors[prereq].append(target)
        indegree[target] += 1

    queue = deque(sorted(code for code in nodes if indegree[code] == 0))
    layer_index = 0

    while queue:
        current = list(queue)
        queue.clear()

        layer_gaps = sorted(
            (by_code[code] for code in current),
            key=lambda g: (-g.gap, -g.confidence, g.skill_code),
        )
        result.layers.append(
            OrderedLayer(
                index=layer_index,
                gaps=layer_gaps,
                note=(
                    "无前置依赖，按能力差距降序"
                    if layer_index == 0
                    else f"依赖第 {layer_index} 阶段的技能，层内按差距降序"
                ),
            )
        )

        for code in current:
            for nxt in successors.get(code, []):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        queue = deque(sorted(queue))
        layer_index += 1

    placed = {g.skill_code for layer in result.layers for g in layer.gaps}
    missing = nodes - placed
    if missing:
        # 理论上不该发生（环已拆解），留作防御
        result.layers.append(
            OrderedLayer(
                index=layer_index,
                gaps=sorted(
                    (by_code[c] for c in missing), key=lambda g: (-g.gap, g.skill_code)
                ),
                note="依赖关系无法解析，置于末尾",
            )
        )
        result.warnings.append(
            f"{len(missing)} 项技能的依赖关系无法解析，已置于最后一阶段"
        )

    return result


def merge_small_layers(
    result: OrderingResult, max_phases: int = 4, min_per_phase: int = 2
) -> OrderingResult:
    """把过多的薄层合并成便于执行的阶段数。

    拓扑层数可能很多（每层一两项），直接当学习阶段会过于琐碎。
    合并时**只合并相邻层**，因此不会破坏前置约束：
    第 k 层的技能永远不会被排到它的前置技能之前。
    """
    if len(result.layers) <= max_phases:
        return result

    merged = OrderingResult(warnings=list(result.warnings), method=result.method)
    bucket: list[SkillGap] = []
    notes: list[str] = []

    # 把 n 层均分到 max_phases 个阶段，保持相邻层的先后
    per_phase = max(min_per_phase, -(-len(result.layers) // max_phases))
    for position, layer in enumerate(result.layers):
        bucket.extend(layer.gaps)
        notes.append(f"拓扑第 {layer.index + 1} 层")
        is_last = position == len(result.layers) - 1
        if (position + 1) % per_phase == 0 or is_last:
            merged.layers.append(
                OrderedLayer(
                    index=len(merged.layers),
                    gaps=sorted(bucket, key=lambda g: (-g.gap, -g.confidence)),
                    note="合并自 " + "、".join(notes) + "，层内按差距降序",
                )
            )
            bucket, notes = [], []

    return merged
