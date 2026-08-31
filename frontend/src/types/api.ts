/**
 * 与后端 app/schemas 对齐的类型定义。
 * 后端改 Schema 时这里必须同步 —— 两边不一致会在编译期暴露，而不是运行期。
 */

// ==================== 枚举（与 backend/app/core/enums.py 一一对应） ====================

export type EvidenceType = 'documentary' | 'statistical'

export type EvidenceSufficiency = 'sufficient' | 'partial' | 'insufficient'

export type SourceTypeCode =
  | 'national_standard'
  | 'teaching_standard'
  | 'industry_spec'
  | 'textbook'
  | 'lab_manual'
  | 'official_doc'
  | 'job_posting'

export type NodeType =
  | 'industry'
  | 'job_family'
  | 'job'
  | 'work_task'
  | 'competency'
  | 'competency_unit'
  | 'skill_point'
  | 'knowledge_point'

export type GraphStatus = 'draft' | 'approved' | 'archived'

export type MasteryLevel = 1 | 2 | 3 | 4

/** 掌握程度的中文标签，与后端 MasteryLevel.label_zh 保持一致 */
export const MASTERY_LABELS: Record<MasteryLevel, string> = {
  1: '了解',
  2: '理解',
  3: '掌握',
  4: '熟练',
}

export const SOURCE_TYPE_LABELS: Record<SourceTypeCode, string> = {
  national_standard: '国家职业技能标准',
  teaching_standard: '专业教学标准',
  industry_spec: '行业规范',
  textbook: '权威教材',
  lab_manual: '实训指导书',
  official_doc: '官方文档',
  job_posting: '公开岗位信息',
}

// ==================== 通用信封 ====================

/** 一条可核验的证据引用 */
export interface SourceRef {
  type: EvidenceType
  marker?: string | null
  chunk_id?: string | null
  posting_id?: string | null
  source_name?: string | null
  source_type?: SourceTypeCode | null
  standard_id?: string | null
  page?: string | null
  section?: string | null
  url?: string | null
  quote?: string | null
  relevance?: number | null
  verified: boolean
}

/**
 * 所有 Agent 输出的统一外壳。
 * 前端渲染任何专业结论时都应展示 sources 与 confidence，
 * evidence_sufficiency === 'insufficient' 时必须显式提示「暂无足够依据」。
 */
export interface AgentEnvelope<T> {
  result: T
  reasoning_summary: string
  sources: SourceRef[]
  confidence: number
  evidence_sufficiency: EvidenceSufficiency
  ai_generated: boolean
  llm_run_id?: string | null
  warnings: string[]
}

export interface ApiErrorDetail {
  code: string
  message: string
  detail: Record<string, unknown>
}

export interface ApiErrorResponse {
  error: ApiErrorDetail
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// ==================== 系统 ====================

export interface ComponentHealth {
  name: string
  ok: boolean
  detail?: string | null
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  app: string
  version: string
  demo_mode: string
  components: ComponentHealth[]
}

export interface ServiceInfo {
  app: string
  version: string
  docs: string
  health: string
}

export const COMPONENT_LABELS: Record<string, string> = {
  database: '数据库',
  llm: '大模型',
  embedding: '向量模型',
  vector_store: '向量库',
}

// ==================== 岗位与技能 ====================
// 注：GraphStatus 已在上方枚举区定义，此处不再重复

export interface Job {
  id: string
  name: string
  job_family?: string | null
  industry?: string | null
  description?: string | null
}

export interface Skill {
  skill_code: string
  name_zh: string
  name_en?: string | null
  category: string
  description?: string | null
  aliases: string[]
  status: 'active' | 'deprecated'
  provenance: string
}
