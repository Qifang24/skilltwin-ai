/** 岗位能力图谱相关类型，与 backend/app/schemas/competency.py 对齐。 */

import type { GraphStatus, MasteryLevel, NodeType, SourceRef } from '@/types/api'

/** 节点的依据引用，回答「这项能力凭什么在图谱里」 */
export interface NodeEvidence {
  chunk_id?: string | null
  page?: string | null
  section?: string | null
  source_name?: string | null
  quote?: string | null
}

export interface GraphNode {
  id: string
  parent_id?: string | null
  node_type: NodeType
  name: string
  description?: string | null
  skill_code?: string | null
  mastery_level?: MasteryLevel | null
  mastery_label?: string | null
  order_index: number
  confidence?: number | null
  /** AI 生成 vs 教师手工添加 */
  ai_generated: boolean
  /** 是否经教师修订过 */
  edited_by_human: boolean
  evidence: NodeEvidence[]
  children: GraphNode[]
}

export interface GraphSummary {
  id: string
  job_id: string
  version: number
  status: GraphStatus
  title?: string | null
  summary?: string | null
  approved_by?: string | null
  approved_at?: string | null
  created_at: string
  node_count: number
  skill_point_count: number
}

export interface GraphDetail extends GraphSummary {
  tree: GraphNode[]
  sources: SourceRef[]
  generation_run_id?: string | null
  warnings: string[]
}

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  industry: '产业',
  job_family: '岗位群',
  job: '岗位',
  work_task: '工作任务',
  competency: '能力',
  competency_unit: '能力单元',
  skill_point: '技能点',
  knowledge_point: '知识点',
}

/**
 * 各层级的配色，用于树图与标签。
 *
 * 相邻层级必须明显可分：早先能力单元用琥珀 #faad14、知识点用橙 #fa8c16，
 * 两者在树上几乎分辨不出，等于白标了颜色。现改为知识点用青色。
 */
export const NODE_TYPE_COLORS: Record<NodeType, string> = {
  industry: '#722ed1', // 紫
  job_family: '#722ed1',
  job: '#1677ff', // 蓝
  work_task: '#fa8c16', // 橙
  competency: '#52c41a', // 绿
  competency_unit: '#faad14', // 琥珀
  skill_point: '#eb2f96', // 品红
  knowledge_point: '#13c2c2', // 青
}

export const GRAPH_STATUS_LABELS: Record<GraphStatus, string> = {
  draft: '草案',
  approved: '已审核',
  archived: '已归档',
}

export const GRAPH_STATUS_COLORS: Record<GraphStatus, string> = {
  draft: 'orange',
  approved: 'green',
  archived: 'default',
}
