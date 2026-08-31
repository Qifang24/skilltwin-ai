/**
 * 能力区间图 —— 这张图才是诚实表达不确定性的地方。
 *
 * 每个技能画一条横向色带，跨度是 95% 置信区间 [score_low, score_high]，
 * 带上的圆点是点估计，竖线是岗位目标要求。
 *
 * 为什么必须有这张图：雷达图只能画点估计，
 * 而「3 题全对得 71.9 分」与「20 题得 83.6 分」在雷达图上看起来差不多，
 * 实际上前者的区间是 [43.9, 100]、后者是 [69.9, 97.2] ——
 * 差别巨大，学生和教师都有权看到。
 *
 * 用堆叠柱实现浮动条：先叠一段透明的到下界，再画可见的区间宽度。
 */

import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'

import type { ProfileEntry } from '@/types/student'

interface SkillIntervalChartProps {
  entries: ProfileEntry[]
  /** 各技能的目标分，用于画目标标记线 */
  targets?: Record<string, number>
  height?: number
}

export function SkillIntervalChart({
  entries,
  targets = {},
  height,
}: SkillIntervalChartProps) {
  const option = useMemo(() => {
    const sorted = [...entries].sort((a, b) => a.score - b.score)
    const names = sorted.map((e) => e.skill_name ?? e.skill_code)

    return {
      grid: { left: 130, right: 40, top: 40, bottom: 30 },
      tooltip: {
        trigger: 'axis' as const,
        axisPointer: { type: 'shadow' as const },
        formatter: (params: { dataIndex: number }[]) => {
          const entry = sorted[params[0]?.dataIndex ?? 0]
          if (!entry) return ''
          const target = targets[entry.skill_code]
          return [
            `<b>${entry.skill_name ?? entry.skill_code}</b>`,
            `估计值：${entry.score.toFixed(1)}`,
            `95% 区间：[${entry.score_low.toFixed(1)}, ${entry.score_high.toFixed(1)}]`,
            `置信度：${entry.confidence.toFixed(2)}${entry.reliable ? '' : '（证据不足）'}`,
            `作答题数：${entry.evidence_count}`,
            target !== undefined ? `岗位目标：${target}` : '',
          ]
            .filter(Boolean)
            .join('<br/>')
        },
      },
      legend: { data: ['95% 置信区间', '估计值', '岗位目标'], top: 0 },
      xAxis: {
        type: 'value' as const,
        min: 0,
        max: 100,
        name: '能力分',
        splitLine: { lineStyle: { type: 'dashed' as const } },
      },
      yAxis: {
        type: 'category' as const,
        data: names,
        axisLabel: { fontSize: 12 },
      },
      series: [
        {
          // 透明垫底：把可见段推到下界位置
          name: '__offset',
          type: 'bar' as const,
          stack: 'interval',
          silent: true,
          itemStyle: { color: 'transparent' },
          data: sorted.map((e) => e.score_low),
          tooltip: { show: false },
        },
        {
          name: '95% 置信区间',
          type: 'bar' as const,
          stack: 'interval',
          barWidth: 14,
          data: sorted.map((e) => ({
            value: e.score_high - e.score_low,
            // 证据不足的区间画得更淡，视觉上就该「虚」一些
            itemStyle: {
              color: e.reliable ? '#91caff' : '#d9d9d9',
              borderRadius: 7,
            },
          })),
        },
        {
          name: '估计值',
          type: 'scatter' as const,
          symbolSize: 11,
          data: sorted.map((e, index) => [e.score, index]),
          itemStyle: { color: '#1677ff' },
          z: 10,
        },
        {
          name: '岗位目标',
          type: 'scatter' as const,
          symbol: 'rect',
          symbolSize: [3, 22],
          data: sorted
            .map((e, index) =>
              targets[e.skill_code] !== undefined
                ? [targets[e.skill_code], index]
                : null,
            )
            .filter(Boolean),
          itemStyle: { color: '#fa541c' },
          z: 11,
        },
      ],
    }
  }, [entries, targets])

  return (
    <ReactECharts
      option={option}
      style={{ height: height ?? Math.max(260, entries.length * 34 + 90), width: '100%' }}
      notMerge
    />
  )
}
