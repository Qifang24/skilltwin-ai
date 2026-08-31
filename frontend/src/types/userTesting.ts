import type { Page } from './api'

export type UserTestRole = 'teacher' | 'student'
export type UserTestSessionStatus = 'draft' | 'completed'
export type UserTestOutcome = 'completed' | 'partial' | 'failed'

export interface UserTestScriptTask {
  code: string
  title: string
  expected_result: string
}

export interface UserTestScript {
  id: string
  name: string
  participant_role: UserTestRole
  description: string
  tasks: UserTestScriptTask[]
}

export interface UserTestTask {
  id: string
  task_code: string
  title: string
  expected_result: string
  order_index: number
  actual_result?: string | null
  outcome?: UserTestOutcome | null
  accuracy?: number | null
  ease_of_use?: number | null
  feedback?: string | null
}

export interface UserTestSession {
  id: string
  participant_alias: string
  participant_role: UserTestRole
  script_id: string
  status: UserTestSessionStatus
  consent_confirmed: boolean
  overall_feedback?: string | null
  completed_at?: string | null
  created_at: string
  tasks: UserTestTask[]
}

export interface UserTestReportTask {
  task_code: string
  title: string
  response_count: number
  completion_rate?: number | null
  average_accuracy?: number | null
  average_ease_of_use?: number | null
  feedback_samples: string[]
}

export interface UserTestReport {
  completed_sessions: number
  draft_sessions: number
  participant_roles: Record<string, number>
  task_records: number
  overall_completion_rate?: number | null
  average_accuracy?: number | null
  average_ease_of_use?: number | null
  tasks: UserTestReportTask[]
  overall_feedback_samples: string[]
  warnings: string[]
  reasoning_summary: string
}

export type UserTestSessionPage = Page<UserTestSession>
