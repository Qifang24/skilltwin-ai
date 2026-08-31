/** Phase 10：岗位市场分析接口类型。所有统计均可回链至 JD 原文证据。 */

export type MarketDataFlag = 'REAL' | 'DEMO'

export interface MarketDataQuality {
  total_postings: number
  real_postings: number
  demo_postings: number
  postings_with_skills: number
  extraction_coverage: number
  missing_posted_at: number
  duplicate_raw_text_count: number
  latest_posted_at: string | null
  warnings: string[]
}

export interface DemandEvidence {
  posting_id: string
  title: string
  company_type: string | null
  city: string | null
  posted_at: string | null
  source_name: string | null
  source_url: string | null
  data_flag: MarketDataFlag
  evidence_span: string
}

export interface SkillDemand {
  skill_code: string
  skill_name: string | null
  category: string | null
  posting_count: number
  total_postings: number
  frequency: number
  real_posting_count: number
  demo_posting_count: number
  is_demo_contaminated: boolean
  evidence: DemandEvidence[]
}

export interface SkillTrendPoint {
  window_start: string
  window_end: string
  posting_count: number
  total_postings: number
  frequency: number
  real_posting_count: number
  demo_posting_count: number
}

export interface SkillTrendSeries {
  skill_code: string
  skill_name: string | null
  points: SkillTrendPoint[]
}

export interface JobMarketDashboard {
  job_id: string
  job_name: string
  data_quality: MarketDataQuality
  ranking: SkillDemand[]
  trends: SkillTrendSeries[]
  computed_at: string | null
  analysis_method: 'deterministic_rule_match'
}

export interface JobMarketAnalyzeResponse {
  dashboard: JobMarketDashboard
  extracted_skill_links: number
  snapshots_written: number
  reasoning_summary: string
  warnings: string[]
}
