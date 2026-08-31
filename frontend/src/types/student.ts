/** 学生、测评与能力画像类型，与 backend/app/schemas/assessment.py 对齐。 */

import type { LearningPathAdaptation } from '@/types/learning'

export type ItemType = 'single' | 'multi' | 'judge' | 'short' | 'code'
export type AssessmentType = 'diagnostic' | 'task' | 'retest'
export type AssessmentStatus = 'in_progress' | 'submitted' | 'scored'
export type ProfileSource = 'diagnostic' | 'task' | 'manual' | 'merged'

export const ITEM_TYPE_LABELS: Record<ItemType, string> = {
  single: '单选',
  multi: '多选',
  judge: '判断',
  short: '简答',
  code: '编程',
}

export interface Student {
  id: string
  display_name: string
  target_job_id?: string | null
  cohort?: string | null
  created_at: string
}

export interface AssessmentItem {
  id: string
  stem: string
  item_type: ItemType
  options: { key: string; text: string }[]
  difficulty: number
  skill_codes: string[]
}

export interface Assessment {
  id: string
  student_id: string
  job_id: string
  type: AssessmentType
  status: AssessmentStatus
  started_at?: string | null
  submitted_at?: string | null
  items: AssessmentItem[]
  /** 开考前的统计效力提示 */
  notes: string[]
}

export interface ProfileEntry {
  skill_code: string
  skill_name?: string | null
  category?: string | null
  score: number
  score_low: number
  score_high: number
  confidence: number
  evidence_count: number
  method: string
  /** 置信度足够时才应展示点估计；否则展示区间 */
  reliable: boolean
}

export interface SkillProfile {
  id: string
  student_id: string
  job_id?: string | null
  source: ProfileSource
  assessment_id?: string | null
  computed_at?: string | null
  entries: ProfileEntry[]
  notes: string[]
}

export interface SkillGap {
  skill_code: string
  skill_name?: string | null
  category?: string | null
  target_score: number
  current_score: number
  gap: number
  confidence: number
  evidence_count: number
  reliable: boolean
  /** 该技能尚未被任何题目考查 */
  untested: boolean
}

export interface SkillGapReport {
  student_id: string
  job_id: string
  graph_id?: string | null
  profile_id?: string | null
  gaps: SkillGap[]
  notes: string[]
}

export interface SubmitResult {
  assessment_id: string
  profile_id: string
  correct_count: number
  total_count: number
  /** 本次测评真正更新的技能 */
  updated_skill_codes: string[]
  /** 从上一份同岗位画像继承、此次未重新测量的技能 */
  inherited_skill_codes: string[]
  learning_path_update?: LearningPathAdaptation | null
  profile: SkillProfile
}

/** 掌握程度换算的目标分，与后端 MASTERY_TO_SCORE 一致 */
export const MASTERY_TO_SCORE: Record<number, number> = {
  1: 40,
  2: 60,
  3: 80,
  4: 90,
}
