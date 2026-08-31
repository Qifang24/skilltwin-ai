import type { EvidenceSufficiency, SourceRef } from './api'
export interface TutorReply { conversation_id: string; answer: { id: number; role: string; content: string; sources: SourceRef[]; created_at: string }; reasoning_summary: string; confidence: number; evidence_sufficiency: EvidenceSufficiency; warnings: string[] }
