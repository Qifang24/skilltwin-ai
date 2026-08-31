/**
 * 后端 API 客户端。
 *
 * 开发期通过 vite 代理走相对路径 /api/v1，因此不需要在前端配置后端地址；
 * 部署时若前后端分离，设置 VITE_API_BASE_URL 即可。
 */

import axios, { AxiosError } from 'axios'

import type {
  ApiErrorResponse,
  GraphStatus,
  HealthResponse,
  Page,
  Skill,
} from '@/types/api'
import type { GraphDetail, GraphNode, GraphSummary } from '@/types/graph'
import type {
  GenerateLearningPathResponse,
  LearningPath,
  PathStatus,
  StartPathRetestResponse,
} from '@/types/learning'
import type {
  TaskDifficulty,
  TaskStatus,
  TrainingTaskDetail,
  TrainingTaskSummary,
} from '@/types/training'
import type {
  Assessment,
  SkillGapReport,
  SkillProfile,
  Student,
  SubmitResult,
} from '@/types/student'
import type {
  JobMarketAnalyzeResponse,
  JobMarketDashboard,
} from '@/types/jobMarket'
import type { CurriculumGapDashboard, CurriculumOptimization } from '@/types/curriculum'
import type { TutorReply } from '@/types/tutor'
import type {
  UserTestOutcome,
  UserTestReport,
  UserTestScript,
  UserTestSession,
  UserTestSessionPage,
} from '@/types/userTesting'

export const API_PREFIX = '/api/v1'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 180_000, // Agent 生成类接口耗时较长
  headers: { 'Content-Type': 'application/json' },
})

/** 从后端统一错误信封里取出可读信息；网络层失败则给出明确提示。 */
export function toErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiErrorResponse>
    const payload = axiosError.response?.data
    if (payload?.error?.message) {
      return payload.error.message
    }
    if (axiosError.code === 'ECONNABORTED') {
      return '请求超时，请稍后重试'
    }
    if (!axiosError.response) {
      return '无法连接后端服务，请确认 uvicorn 已在 127.0.0.1:8000 启动'
    }
    return `请求失败（HTTP ${axiosError.response.status}）`
  }
  return error instanceof Error ? error.message : '未知错误'
}

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(error),
)

// ==================== 系统 ====================

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>(`${API_PREFIX}/health`)
  return data
}

// ==================== 用户测试 ====================

export async function fetchUserTestScripts() {
  const { data } = await http.get<UserTestScript[]>(`${API_PREFIX}/user-testing/scripts`)
  return data
}

export async function fetchUserTestSessions() {
  const { data } = await http.get<UserTestSessionPage>(`${API_PREFIX}/user-testing/sessions`)
  return data
}

export async function createUserTestSession(payload: {
  participant_alias: string
  participant_role: 'teacher' | 'student'
  script_id: string
  consent_confirmed: boolean
}) {
  const { data } = await http.post<UserTestSession>(`${API_PREFIX}/user-testing/sessions`, payload)
  return data
}

export async function updateUserTestTask(taskId: string, payload: {
  actual_result: string
  outcome: UserTestOutcome
  accuracy: number
  ease_of_use: number
  feedback?: string
}) {
  const { data } = await http.patch(`${API_PREFIX}/user-testing/tasks/${taskId}`, payload)
  return data
}

export async function completeUserTestSession(sessionId: string, overall_feedback?: string) {
  const { data } = await http.post<UserTestSession>(`${API_PREFIX}/user-testing/sessions/${sessionId}/complete`, { overall_feedback })
  return data
}

export async function deleteUserTestSession(sessionId: string) {
  await http.delete(`${API_PREFIX}/user-testing/sessions/${sessionId}`)
}

export async function fetchUserTestReport() {
  const { data } = await http.get<UserTestReport>(`${API_PREFIX}/user-testing/report`)
  return data
}

// ==================== 技能表 ====================

export async function fetchSkills(params?: { category?: string; limit?: number }) {
  const { data } = await http.get<Page<Skill>>(`${API_PREFIX}/skills`, { params })
  return data
}

// ==================== 岗位能力图谱 ====================

export async function fetchGraphs(params?: { job_id?: string; status?: GraphStatus }) {
  const { data } = await http.get<Page<GraphSummary>>(`${API_PREFIX}/graphs`, { params })
  return data
}

export async function fetchGraph(graphId: string) {
  const { data } = await http.get<GraphDetail>(`${API_PREFIX}/graphs/${graphId}`)
  return data
}

/** 生成图谱草案。耗时较长（含检索与模型生成），可达 1 分钟。 */
export async function generateGraph(jobId: string, focus?: string) {
  const { data } = await http.post<GraphDetail>(`${API_PREFIX}/graphs/generate`, {
    job_id: jobId,
    focus,
  })
  return data
}

export async function approveGraph(graphId: string, approvedBy: string) {
  const { data } = await http.post<GraphSummary>(
    `${API_PREFIX}/graphs/${graphId}/approve`,
    { approved_by: approvedBy },
  )
  return data
}

export interface NodeUpdatePayload {
  name?: string
  description?: string | null
  skill_code?: string | null
  mastery_level?: number | null
}

export async function updateGraphNode(
  graphId: string,
  nodeId: string,
  payload: NodeUpdatePayload,
) {
  const { data } = await http.patch<GraphNode>(
    `${API_PREFIX}/graphs/${graphId}/nodes/${nodeId}`,
    payload,
  )
  return data
}

export async function deleteGraphNode(graphId: string, nodeId: string) {
  const { data } = await http.delete<{ removed: number }>(
    `${API_PREFIX}/graphs/${graphId}/nodes/${nodeId}`,
  )
  return data
}

export async function fetchTargetVector(graphId: string) {
  const { data } = await http.get<Record<string, number>>(
    `${API_PREFIX}/graphs/${graphId}/target-vector`,
  )
  return data
}

// ==================== 实训任务 ====================

export async function fetchTasks(params?: { job_id?: string; status?: TaskStatus }) {
  const { data } = await http.get<Page<TrainingTaskSummary>>(
    `${API_PREFIX}/training-tasks`,
    { params },
  )
  return data
}

export async function fetchTask(taskId: string) {
  const { data } = await http.get<TrainingTaskDetail>(
    `${API_PREFIX}/training-tasks/${taskId}`,
  )
  return data
}

/** 从能力节点生成实训任务。只能用已审核图谱的节点。 */
export async function generateTask(
  nodeId: string,
  difficulty: TaskDifficulty = 'beginner',
  context?: string,
) {
  const { data } = await http.post<TrainingTaskDetail>(
    `${API_PREFIX}/training-tasks/generate`,
    { node_id: nodeId, difficulty, context },
  )
  return data
}

export async function publishTask(taskId: string, publishedBy: string) {
  const { data } = await http.post<TrainingTaskSummary>(
    `${API_PREFIX}/training-tasks/${taskId}/publish`,
    { published_by: publishedBy },
  )
  return data
}

// ==================== 学生与测评 ====================

export async function fetchStudents() {
  const { data } = await http.get<Student[]>(`${API_PREFIX}/students`)
  return data
}

export async function createStudent(payload: {
  display_name: string
  target_job_id?: string
  cohort?: string
}) {
  const { data } = await http.post<Student>(`${API_PREFIX}/students`, payload)
  return data
}

export async function deleteStudent(studentId: string) {
  const { data } = await http.delete<{ deleted: string }>(
    `${API_PREFIX}/students/${studentId}`,
  )
  return data
}

export async function startAssessment(
  studentId: string,
  jobId: string,
  itemCount = 16,
  type: 'diagnostic' | 'task' | 'retest' = 'diagnostic',
) {
  const { data } = await http.post<Assessment>(
    `${API_PREFIX}/students/${studentId}/assessments`,
    { job_id: jobId, item_count: itemCount, type },
  )
  return data
}

export async function fetchAssessment(assessmentId: string) {
  const { data } = await http.get<Assessment>(
    `${API_PREFIX}/assessments/${assessmentId}`,
  )
  return data
}

export async function submitAssessment(
  assessmentId: string,
  responses: { item_id: string; response: string[] }[],
) {
  const { data } = await http.post<SubmitResult>(
    `${API_PREFIX}/assessments/${assessmentId}/submit`,
    { responses },
  )
  return data
}

export async function fetchProfile(studentId: string, jobId?: string) {
  const { data } = await http.get<SkillProfile>(
    `${API_PREFIX}/students/${studentId}/skill-profile`,
    { params: jobId ? { job_id: jobId } : undefined },
  )
  return data
}

export async function fetchGap(studentId: string, jobId?: string) {
  const { data } = await http.get<SkillGapReport>(
    `${API_PREFIX}/students/${studentId}/skill-gap`,
    { params: jobId ? { job_id: jobId } : undefined },
  )
  return data
}

// ==================== 个性化学习路径 ====================

export async function fetchLatestLearningPath(
  studentId: string,
  jobId?: string,
): Promise<LearningPath | null> {
  try {
    const { data } = await http.get<LearningPath>(
      `${API_PREFIX}/students/${studentId}/learning-paths/latest`,
      { params: jobId ? { job_id: jobId } : undefined },
    )
    return data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

export async function generateLearningPath(
  studentId: string,
  jobId: string,
  maxPhases = 4,
) {
  const { data } = await http.post<GenerateLearningPathResponse>(
    `${API_PREFIX}/students/${studentId}/learning-paths/generate`,
    { job_id: jobId, max_phases: maxPhases },
  )
  return data
}

export async function updateLearningPathItem(
  studentId: string,
  itemId: string,
  status: PathStatus,
  note?: string,
) {
  const { data } = await http.patch<LearningPath>(
    `${API_PREFIX}/students/${studentId}/learning-path-items/${itemId}`,
    { status, note },
  )
  return data
}

export async function startLearningPathRetest(
  studentId: string,
  itemId: string,
  itemCount = 16,
) {
  const { data } = await http.post<StartPathRetestResponse>(
    `${API_PREFIX}/students/${studentId}/learning-path-items/${itemId}/retest`,
    { item_count: itemCount },
  )
  return data
}

// ==================== 岗位市场分析 ====================

export async function fetchJobMarketDashboard(
  jobId: string,
  params?: { top_n?: number; trend_skill_code?: string[] },
) {
  const { data } = await http.get<JobMarketDashboard>(
    `${API_PREFIX}/job-market/${jobId}/dashboard`,
    { params },
  )
  return data
}

/** 使用已导入 JD 的原文精确匹配重建统计，不调用 LLM。 */
export async function analyzeJobMarket(jobId: string) {
  const { data } = await http.post<JobMarketAnalyzeResponse>(
    `${API_PREFIX}/job-market/${jobId}/analyze`,
  )
  return data
}

export async function fetchCurriculumGap(jobId: string) {
  const { data } = await http.get<CurriculumGapDashboard>(`${API_PREFIX}/curriculum/${jobId}/gap`)
  return data
}

export async function fetchCurriculumOptimization(jobId: string) {
  const { data } = await http.get<CurriculumOptimization>(`${API_PREFIX}/curriculum/${jobId}/optimization`)
  return data
}

export async function sendTutorMessage(studentId: string, payload: { message: string; job_id: string; task_id?: string; conversation_id?: string }) {
  const { data } = await http.post<TutorReply>(`${API_PREFIX}/students/${studentId}/tutor/chat`, payload)
  return data
}
