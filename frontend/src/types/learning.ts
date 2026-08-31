/** 个性化学习路径类型，与 backend/app/schemas/learning.py 对齐。 */

import type { EvidenceSufficiency, SourceRef } from '@/types/api'

export type PathStatus = 'active' | 'completed' | 'skipped' | 'archived'
export type PathItemType = 'knowledge' | 'task' | 'assessment' | 'practice'

export const PATH_STATUS_LABELS: Record<PathStatus, string> = {
  active: '进行中',
  completed: '已完成',
  skipped: '已跳过',
  archived: '已归档',
}

export const PATH_STATUS_COLORS: Record<PathStatus, string> = {
  active: 'blue',
  completed: 'green',
  skipped: 'default',
  archived: 'default',
}

export const PATH_ITEM_LABELS: Record<PathItemType, string> = {
  knowledge: '知识学习',
  task: '实训任务',
  assessment: '阶段复测',
  practice: '行动建议',
}

export interface LearningPathActivity {
  id: string
  action: string
  previous_status?: PathStatus | null
  new_status?: PathStatus | null
  ref_type?: string | null
  ref_id?: string | null
  note?: string | null
  created_at: string
}

export interface LearningPathProgress {
  total_items: number
  completed_items: number
  skipped_items: number
  done_items: number
  percent: number
}

export interface LearningPathItem {
  id: string
  order_index: number
  item_type: PathItemType
  title: string
  description?: string | null
  ref_id?: string | null
  skill_code?: string | null
  status: PathStatus
  completed_at?: string | null
  extra: Record<string, unknown>
  activities: LearningPathActivity[]
}

export interface LearningPathPhase {
  id: string
  order_index: number
  title: string
  description?: string | null
  target_skill_codes: string[]
  est_hours?: number | null
  status: PathStatus
  ordering_note?: string | null
  items: LearningPathItem[]
  progress: LearningPathProgress
}

export interface LearningPath {
  id: string
  student_id: string
  job_id: string
  profile_id?: string | null
  graph_id?: string | null
  title?: string | null
  rationale?: string | null
  status: PathStatus
  ordering_method?: string | null
  warnings: string[]
  generation_run_id?: string | null
  created_at: string
  updated_at: string
  phases: LearningPathPhase[]
  progress: LearningPathProgress
}

export interface GenerateLearningPathResponse {
  path: LearningPath
  reasoning_summary: string
  sources: SourceRef[]
  confidence: number
  evidence_sufficiency: EvidenceSufficiency
  ai_generated: boolean
  warnings: string[]
}

export interface StartPathRetestResponse {
  assessment_id: string
  student_id: string
  job_id: string
  notes: string[]
}

export interface LearningPathAdaptation {
  linked_item_id?: string | null
  archived_path_id?: string | null
  new_path_id?: string | null
  recalculated: boolean
  message: string
  warnings: string[]
}
