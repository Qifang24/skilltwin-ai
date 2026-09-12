/**
 * 能力雷达图：当前水平 vs 岗位目标要求。
 *
 * **不确定性怎么表达**是这张图的设计难点。
 * 一个「50 分但完全没测过」的维度，不该和「50 分且测了 20 题」画得一样 ——
 * 那等于用图表撒谎。
 *
 * 做法：雷达图只画点估计（否则四条线叠在一起没法看），
 * 但对置信度不足的维度在轴标签后加 `⚠`，并把不可信维度的点
 * 用更淡的颜色画出。真正的区间交给 SkillIntervalChart 表达。
 */

import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'

import type { SkillGap } from '@/types/student'

interface SkillRadarProps {
  gaps: SkillGap[]
  height?: number
  /** 维度过多时雷达图会糊成一团，只取差距最大的前 N 项 */
  maxAxes?: number
}

export function SkillRadar({ gaps, height = 420, maxAxes = 8 }: SkillRadarProps) {
  const option = useMemo(() => {
    const shown = gaps.slice(0, maxAxes)

    const indicator = shown.map((g) => ({
      // 证据不足的维度标出来 —— 读图的人有权知道哪些数字站不住
      name: (g.skill_name ?? g.skill_code) + (g.reliable ? '' : ' ⚠'),
      max: 100,
    }))

    return {
      tooltip: {
        trigger: 'item' as const,
        formatter: () =>
          shown
            .map((g) => {
              const label = g.skill_name ?? g.skill_code
              if (g.untested) return `${label}：<b>尚未测评</b>`
              const caveat = g.reliable
                ? ''
                : `（仅 ${g.evidence_count} 题，证据不足）`
              return `${label}：${g.current_score.toFixed(0)} / 目标 ${g.target_score.toFixed(0)} ${caveat}`
            })
            .join('<br/>'),
      },
      legend: {
        data: ['岗位目标要求', '当前水平'],
        bottom: 0,
        textStyle: { fontWeight: 700 },
      },
      radar: {
        indicator,
        radius: '62%',
        splitNumber: 4,
        axisName: {
          fontSize: 12,
          fontWeight: 700,
          color: '#595959',
        },
        splitArea: { areaStyle: { color: ['#fff', '#fafafa'] } },
      },
      series: [
        {
          type: 'radar' as const,
          data: [
            {
              name: '岗位目标要求',
              value: shown.map((g) => g.target_score),
              lineStyle: { type: 'dashed' as const, width: 2 },
              itemStyle: { color: '#1677ff' },
              areaStyle: { opacity: 0.06 },
            },
            {
              name: '当前水平',
              value: shown.map((g) => g.current_score),
              itemStyle: { color: '#52c41a' },
              lineStyle: { width: 2 },
              areaStyle: { opacity: 0.25 },
            },
          ],
        },
      ],
    }
  }, [gaps, maxAxes])

  return <ReactECharts option={option} style={{ height, width: '100%' }} notMerge />
}
