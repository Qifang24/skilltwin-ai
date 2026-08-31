/** 实训任务类型，与 backend/app/schemas/training.py 对齐。 */

export type TaskDifficulty = 'beginner' | 'intermediate' | 'advanced'
export type TaskStatus = 'draft' | 'published' | 'archived'

export const DIFFICULTY_LABELS: Record<TaskDifficulty, string> = {
  beginner: '入门',
  intermediate: '进阶',
  advanced: '挑战',
}

export const DIFFICULTY_COLORS: Record<TaskDifficulty, string> = {
  beginner: 'green',
  intermediate: 'orange',
  advanced: 'red',
}

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  draft: '草案',
  published: '已发布',
  archived: '已归档',
}

export const TASK_STATUS_COLORS: Record<TaskStatus, string> = {
  draft: 'orange',
  published: 'green',
  archived: 'default',
}

export interface TaskObjective {
  text: string
  skill_code?: string | null
}

export interface TaskStep {
  order: number
  title: string
  detail: string
  hint?: string | null
}

export interface RubricLevel {
  level: string
  criteria: string
}

export interface RubricDimension {
  dimension: string
  weight: number
  levels: RubricLevel[]
}

export interface CommonMistake {
  mistake: string
  consequence: string
  fix: string
}

export interface TaskCitation {
  chunk_id?: string | null
  source_name?: string | null
  page?: string | null
  section?: string | null
  quote?: string | null
}

export interface TaskSkill {
  skill_code: string
  weight: number
  target_level?: number | null
  skill_name?: string | null
}

export interface TrainingTaskSummary {
  id: string
  job_id: string
  source_node_id?: string | null
  title: string
  difficulty: TaskDifficulty
  est_minutes?: number | null
  status: TaskStatus
  ai_generated: boolean
  edited_by_human: boolean
  published_by?: string | null
  skill_count: number
}

export interface TrainingTaskDetail extends TrainingTaskSummary {
  scenario: string
  objectives: TaskObjective[]
  steps: TaskStep[]
  deliverables: string[]
  rubric: RubricDimension[]
  common_mistakes: CommonMistake[]
  extensions: string[]
  safety_notes?: string | null
  citations: TaskCitation[]
  skills: TaskSkill[]
  generation_run_id?: string | null
  warnings: string[]
  source_node_name?: string | null
}
