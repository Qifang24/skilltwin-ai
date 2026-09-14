/**
 * 后端 API 客户端。
 *
 * 开发期通过 vite 代理走相对路径 /api/v1，因此不需要在前端配置后端地址；
 * Vercel Services 同域部署时仍走相对路径；只有分开部署时才设置 VITE_API_BASE_URL。
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
  JobEvidenceCandidate,
  JobPostingImportPayload,
  JobPostingImportResponse,
} from '@/types/jobMarket'
import type { CurriculumGapDashboard, CurriculumOptimization } from '@/types/curriculum'
import type { CurriculumAnalysis, CurriculumDraftCourse, CurriculumImportBatch, CurriculumPlanDetail, CourseSkillMapping, EvidenceChain, ImportRowState, JobImportBatch, JobImportResult, OptimizationRun, OptimizationSuggestion, ScopeOption } from '@/types/professional'
import type { TutorReply } from '@/types/tutor'
import type {
  UserTestOutcome,
  UserTestReport,
  UserTestScript,
  UserTestSession,
  UserTestSessionPage,
} from '@/types/userTesting'

export const API_PREFIX = '/api/v1'
export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_UPLOAD_MAX_MB ?? 10)

type UnknownRecord = Record<string, unknown>
interface RawImportRow extends UnknownRecord {
  row_number?: number
  status?: string
  normalized_data?: Record<string, string | number | boolean | null>
  data?: Record<string, string | number | boolean | null>
  errors?: string[]
  warnings?: string[]
}
interface RawJobImport extends UnknownRecord {
  id?: string
  job_id?: string
  job_name?: string
  status?: string
  headers?: string[]
  field_mapping?: Record<string, string>
  mapping?: Record<string, string>
  total_rows?: number
  success_count?: number
  failed_count?: number
  duplicate_count?: number
  filtered_count?: number
  rows?: RawImportRow[]
}

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
      return '无法连接后端服务，请检查 API 地址和服务状态'
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
export async function generateGraph(jobId: string, focus?: string, selectedSkillCodes?: string[]) {
  const { data } = await http.post<GraphDetail>(`${API_PREFIX}/graphs/generate`, {
    job_id: jobId,
    focus,
    selected_skill_codes: selectedSkillCodes ?? [],
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
  teacher_note?: string | null
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
  curriculum?: { planId?: string; courseId?: string },
) {
  const { data } = await http.post<TrainingTaskDetail>(
    `${API_PREFIX}/training-tasks/generate`,
    {
      node_id: nodeId,
      difficulty,
      context,
      ...(curriculum?.planId ? { plan_id: curriculum.planId } : {}),
      ...(curriculum?.courseId ? { course_id: curriculum.courseId } : {}),
    },
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
  params?: {
    top_n?: number
    trend_skill_code?: string[]
    city?: string
    source?: string
    title?: string
    posted_from?: string
    posted_to?: string
  },
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

export async function refreshTaskCitations(taskId: string) {
  const { data } = await http.post<TrainingTaskDetail>(
    `${API_PREFIX}/training-tasks/${taskId}/refresh-citations`,
  )
  return data
}

export async function updateTask(taskId: string, payload: Record<string, unknown>) {
  const { data } = await http.patch<TrainingTaskDetail>(
    `${API_PREFIX}/training-tasks/${taskId}`,
    payload,
  )
  return data
}

export async function fetchGraphNodeJobEvidenceCandidates(graphId: string, nodeId: string) {
  const { data } = await http.get<JobEvidenceCandidate[]>(
    `${API_PREFIX}/graphs/${graphId}/nodes/${nodeId}/job-evidence-candidates`,
  )
  return data
}

export async function linkGraphNodeJobEvidence(graphId: string, nodeId: string, postingIds: string[]) {
  const { data } = await http.post<GraphNode>(
    `${API_PREFIX}/graphs/${graphId}/nodes/${nodeId}/job-evidence`,
    { posting_ids: postingIds },
  )
  return data
}

export async function importJobPostings(payload: JobPostingImportPayload) {
  const { data } = await http.post<JobPostingImportResponse>(`${API_PREFIX}/job-market/import`, payload)
  return data
}

// ==================== 专业建设闭环（批次化导入、对标、优化） ====================
// Uploads deliberately use FormData; callers can retry each stage without re-uploading.
export async function createJobImport(file: File, jobId = 'ai_data_annotator', jobName = 'AI 数据标注工程师'): Promise<JobImportBatch> {
  const form = new FormData(); form.append('file', file); form.append('job_id', jobId); form.append('job_name', jobName)
  const { data } = await http.post<RawJobImport>(`${API_PREFIX}/job-imports`, form, { headers: { 'Content-Type': undefined } })
  return normalizeJobImport(data)
}
export async function updateJobImportMapping(batchId: string, mapping: Record<string, string>, jobName?: string) {
  const { data } = await http.patch<RawJobImport>(`${API_PREFIX}/job-imports/${batchId}/mapping`, { mapping, job_name: jobName })
  return normalizeJobImport(data)
}
export async function fetchJobImportPreview(batchId: string) {
  const { data } = await http.get<RawJobImport>(`${API_PREFIX}/job-imports/${batchId}/preview`)
  return normalizeJobImport(data)
}
export async function confirmJobImport(batchId: string) {
  const { data } = await http.post<RawJobImport>(`${API_PREFIX}/job-imports/${batchId}/confirm`)
  const batch = normalizeJobImport(data)
  return { batch_id: batch.id, job_id: batch.job_id ?? '', job_name: batch.job_name ?? undefined, created: data.success_count ?? 0, updated: 0, skipped_duplicates: data.duplicate_count ?? 0, filtered: data.filtered_count ?? 0, failed: data.failed_count ?? 0, pii_scrubbed: batch.rows?.filter((row) => row.data.pii_scrubbed === true).length ?? 0, rows: batch.rows ?? [], warnings: [] } satisfies JobImportResult
}
export async function fetchJobImportResult(batchId: string) {
  const { data } = await http.get<RawJobImport>(`${API_PREFIX}/job-imports/${batchId}/result`)
  const batch = normalizeJobImport(data)
  return { batch_id: batch.id, job_id: batch.job_id ?? '', job_name: batch.job_name ?? undefined, created: data.success_count ?? 0, updated: 0, skipped_duplicates: data.duplicate_count ?? 0, filtered: data.filtered_count ?? 0, failed: data.failed_count ?? 0, pii_scrubbed: 0, rows: batch.rows ?? [], warnings: [] } satisfies JobImportResult
}

function normalizeJobImport(raw: RawJobImport): JobImportBatch {
  const rows = (raw.rows ?? []).map((row) => {
    const state: ImportRowState = row.status === 'invalid' ? 'error' : row.status === 'duplicate' ? 'duplicate' : row.status === 'imported' ? 'imported' : row.warnings?.length ? 'warning' : 'valid'
    return { row_number: row.row_number ?? 0, state, data: row.normalized_data ?? row.data ?? {}, issues: [...(row.errors ?? []), ...(row.warnings ?? [])].map((message) => ({ message })), dedupe_match_id: null }
  })
  return { id: raw.id ?? '', job_id: raw.job_id ?? null, job_name: raw.job_name ?? null, status: raw.status ?? 'unknown', headers: raw.headers ?? [], mapping: raw.field_mapping ?? raw.mapping ?? {}, total_rows: raw.total_rows ?? rows.length, preview_rows: rows, rows }
}
export async function fetchJobPostings(jobId: string) {
  const { data } = await http.get(`${API_PREFIX}/job-market/${jobId}/postings`)
  return data
}
export async function fetchMarketJobs(): Promise<{ id: string; name: string }[]> {
  const { data } = await http.get<{ id: string; name: string }[]>(`${API_PREFIX}/job-market/jobs`); return data
}

export async function fetchCurriculumPlans(): Promise<ScopeOption[]> {
  const { data } = await http.get<ScopeOption[]>(`${API_PREFIX}/curriculum/plans`); return data
}
export async function deleteCurriculumPlan(planId: string) {
  await http.delete(`${API_PREFIX}/curriculum/plans/${planId}`)
}
export async function fetchCurriculumPlan(planId: string): Promise<CurriculumPlanDetail> {
  const [{ data: plan }, { data: courses }] = await Promise.all([http.get(`${API_PREFIX}/curriculum/plans/${planId}`), http.get(`${API_PREFIX}/curriculum/plans/${planId}/courses`)]); return { ...plan, courses }
}
function normalizeCurriculumImport(value: unknown): CurriculumImportBatch {
  const raw = value as UnknownRecord
  const courses = (Array.isArray(raw.courses) ? raw.courses : []).map((item, index) => {
    const row = item as UnknownRecord
    const data = (row.data ?? row) as UnknownRecord
    return { ...data, id: typeof row.id === 'string' ? row.id : typeof data.id === 'string' ? data.id : `draft-${index + 1}`, evidence: (row.field_evidence ?? row.evidence ?? {}) as CurriculumDraftCourse['evidence'], name: typeof data.name === 'string' ? data.name : '', total_hours: typeof data.total_hours === 'number' ? data.total_hours : null, objectives: typeof data.objectives === 'string' ? data.objectives : null }
  })
  return { id: typeof raw.id === 'string' ? raw.id : '', status: typeof raw.status === 'string' ? raw.status : 'unknown', file_name: typeof raw.filename === 'string' ? raw.filename : undefined, plan_id: typeof raw.confirmed_plan_id === 'string' ? raw.confirmed_plan_id : null, plan_name: typeof raw.source_name === 'string' ? raw.source_name : null, warnings: typeof raw.error_message === 'string' ? [raw.error_message] : [], courses }
}
export async function createCurriculumImport(file: File, planName?: string): Promise<CurriculumImportBatch> {
  const form = new FormData(); form.append('file', file); form.append('source_name', planName || file.name)
  const { data } = await http.post<unknown>(`${API_PREFIX}/curriculum/imports`, form, { headers: { 'Content-Type': undefined } }); return normalizeCurriculumImport(data)
}
export async function fetchCurriculumImportPreview(batchId: string) {
  const { data } = await http.get<unknown>(`${API_PREFIX}/curriculum/imports/${batchId}/preview`); return normalizeCurriculumImport(data)
}
export async function retryCurriculumImport(batchId: string) {
  const { data } = await http.post<unknown>(`${API_PREFIX}/curriculum/imports/${batchId}/retry`); return normalizeCurriculumImport(data)
}
export async function confirmCurriculumImport(batchId: string, input?: { plan_id?: string; name?: string }) {
  const body = { plan_id: input?.plan_id || `plan_${batchId}`, name: input?.name || '导入培养方案', profession: null, version: null, is_partial: false }
  const { data } = await http.post<{ id: string }>(`${API_PREFIX}/curriculum/imports/${batchId}/confirm`, body); return fetchCurriculumPlan(data.id)
}
export async function createCurriculumAnalysis(payload: { job_id: string; plan_id: string; graph_id: string }) {
  const { data } = await http.post<CurriculumAnalysis>(`${API_PREFIX}/curriculum/analyses`, payload); return data
}
export async function fetchCurriculumAnalysis(params: { job_id: string; plan_id: string; graph_id: string }) {
  const { data } = await http.get<unknown>(`${API_PREFIX}/curriculum/analyses`, { params }); return normalizeAnalysis(data)
}
function normalizeAnalysis(value: unknown): CurriculumAnalysis { return value as CurriculumAnalysis }
function normalizeRun(value: unknown): OptimizationRun { return value as OptimizationRun }
export async function createCourseSkillMapping(courseId: string, payload: Partial<CourseSkillMapping>) {
  const { data } = await http.post<CourseSkillMapping>(`${API_PREFIX}/curriculum/courses/${courseId}/skills`, { evidence_quote: '', ...payload }); return data
}
export async function updateCourseSkillMapping(mappingId: string, payload: Partial<CourseSkillMapping>) {
  const { data } = await http.patch<CourseSkillMapping>(`${API_PREFIX}/curriculum/skill-mappings/${mappingId}`, { evidence_quote: '', ...payload }); return data
}
export async function deleteCourseSkillMapping(mappingId: string) { await http.delete(`${API_PREFIX}/curriculum/skill-mappings/${mappingId}`) }
export async function fetchSkillEvidence(params: { job_id: string; plan_id: string; graph_id: string; skill_code: string }) {
  const { data } = await http.get<EvidenceChain>(`${API_PREFIX}/curriculum/evidence`, { params }); return data
}
export async function generateOptimization(payload: { job_id: string; plan_id: string; graph_id: string }) {
  const { data } = await http.post<unknown>(`${API_PREFIX}/curriculum/optimization-runs`, payload); return normalizeRun(data)
}
export async function fetchOptimizationRun(params: { job_id: string; plan_id: string; graph_id: string }) {
  const { data } = await http.get<unknown>(`${API_PREFIX}/curriculum/optimization-runs/latest`, { params }); return normalizeRun(data)
}
export async function updateOptimizationSuggestion(id: string, payload: Partial<Pick<OptimizationSuggestion, 'title' | 'suggestion' | 'action_type' | 'state' | 'teacher_note'>>) {
  const { data } = await http.patch<OptimizationSuggestion>(`${API_PREFIX}/curriculum/optimization-suggestions/${id}`, payload); return data
}
export function optimizationReportUrl(runId: string) { return `${http.defaults.baseURL}${API_PREFIX}/curriculum/optimization-runs/${runId}/report.docx` }

export async function deleteGraph(graphId: string) {
  await http.delete(`${API_PREFIX}/graphs/${graphId}`)
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
