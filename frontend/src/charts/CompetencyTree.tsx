/**
 * 岗位能力图谱树图（ECharts tree series）。
 *
 * 用 tree 而非 force graph：能力分解本身是**层级**关系，
 * 力导向图会把清晰的层级搅成一团毛线，反而看不出「能力如何拆到技能点」。
 */

import ReactECharts from 'echarts-for-react'
import { useMemo, useRef } from 'react'

import type { GraphNode } from '@/types/graph'
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from '@/types/graph'

interface TreeDatum {
  name: string
  value: string // 节点 id，点击时回传
  itemStyle: { color: string; borderColor: string; borderWidth: number }
  label?: Record<string, unknown>
  children?: TreeDatum[]
  collapsed?: boolean
}

function toTreeData(node: GraphNode, selectedId: string | null): TreeDatum {
  const color = NODE_TYPE_COLORS[node.node_type] ?? '#8c8c8c'
  const isSelected = node.id === selectedId

  // 教师改过的节点加个后缀，一眼能看出哪些经过人工修订
  const suffix = node.edited_by_human ? ' ✎' : ''

  return {
    name: node.name + suffix,
    value: node.id,
    itemStyle: {
      color,
      borderColor: isSelected ? '#000' : color,
      borderWidth: isSelected ? 3 : 0,
    },
    label: isSelected ? { fontWeight: 'bold' } : undefined,
    children: node.children.map((child) => toTreeData(child, selectedId)),
  }
}

interface CompetencyTreeProps {
  tree: GraphNode[]
  selectedId: string | null
  onSelect: (nodeId: string) => void
  height?: number
}

export function CompetencyTree({
  tree,
  selectedId,
  onSelect,
  height = 640,
}: CompetencyTreeProps) {
  const chartRef = useRef<ReactECharts>(null)

  const option = useMemo(() => {
    const data = tree.map((root) => toTreeData(root, selectedId))
    return {
      tooltip: {
        trigger: 'item' as const,
        triggerOn: 'mousemove' as const,
        formatter: (params: { name: string }) => params.name,
      },
      series: [
        {
          type: 'tree' as const,
          data,
          top: '2%',
          // 根节点标签渲染在节点左侧，左边距不够会被画布裁掉
          // （实测「AI数据标注工程师」被截成「据标注工程师」）
          left: 140,
          bottom: '2%',
          // 叶子节点标签渲染在右侧，同样需要留出空间
          right: 160,
          symbolSize: 11,
          orient: 'LR' as const,
          initialTreeDepth: -1, // 全展开：教师需要一眼看到完整分解
          label: {
            position: 'left' as const,
            verticalAlign: 'middle' as const,
            align: 'right' as const,
            fontSize: 13,
          },
          leaves: {
            label: {
              position: 'right' as const,
              verticalAlign: 'middle' as const,
              align: 'left' as const,
            },
          },
          emphasis: { focus: 'descendant' as const },
          expandAndCollapse: true,
          animationDuration: 400,
          animationDurationUpdate: 400,
        },
      ],
    }
  }, [tree, selectedId])

  return (
    <ReactECharts
      ref={chartRef}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
      onEvents={{
        click: (params: { data?: { value?: string } }) => {
          if (params.data?.value) onSelect(params.data.value)
        },
      }}
    />
  )
}

/** 层级图例。不标出来的话，颜色只是装饰。 */
export function TreeLegend() {
  const types = [
    'job',
    'competency',
    'competency_unit',
    'skill_point',
    'knowledge_point',
  ] as const

  return (
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12 }}>
      {types.map((type) => (
        <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: NODE_TYPE_COLORS[type],
              display: 'inline-block',
            }}
          />
          {NODE_TYPE_LABELS[type]}
        </span>
      ))}
      <span style={{ color: 'rgba(0,0,0,0.45)' }}>✎ 表示经教师修订</span>
    </div>
  )
}
