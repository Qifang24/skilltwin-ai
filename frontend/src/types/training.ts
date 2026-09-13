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

/** 任务生成时选择的培养方案。旧任务没有此关联，因此所有字段都保持可选。 */
export interface TaskCurriculumPlan {
  id: string
  name: string
  profession?: string | null
  version?: string | null
  source_name?: string | null
  source_url?: string | null
  is_partial?: boolean
}

/** 任务生成时选择的课程教学上下文。 */
export interface TaskCurriculumCourse {
  id: string
  plan_id: string
  course_code?: string | null
  name: string
  category?: string | null
  total_hours?: number | null
  objectives?: string | null
  description?: string | null
  teaching_content?: string | null
  knowledge_points?: string | null
  practical_content?: string | null
  learning_outcomes?: string | null
}

/** 可回看导入材料原文的课程依据。 */
export interface TaskCourseEvidence {
  evidence_type: 'course_source' | 'course_field' | 'skill_coverage' | string
  field?: string | null
  skill_code?: string | null
  chunk_id?: string | null
  page?: string | null
  quote: string
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
  /** 可空以兼容在课程关联功能上线前生成的任务。 */
  plan_id?: string | null
  course_id?: string | null
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
  curriculum_plan?: TaskCurriculumPlan | null
  curriculum_course?: TaskCurriculumCourse | null
  course_evidence?: TaskCourseEvidence[]
}
