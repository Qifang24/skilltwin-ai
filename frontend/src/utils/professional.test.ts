import { describe, expect, it } from 'vitest'

import { coveragePresentation, filterSuggestions, importRowPresentation, nextSuggestionState } from '@/utils/professional'
import type { OptimizationSuggestion } from '@/types/professional'

const suggestion = (id: string, state: OptimizationSuggestion['state']): OptimizationSuggestion => ({
  id, state, skill_code: 'data_cleaning', priority: 'high', priority_score: 80,
  action_type: 'add', title: '补齐数据清洗', suggestion: '新增练习', coverage_status: 'uncovered',
  posting_count: 12, affected_courses: [], generation_reason: '高需求但未覆盖', ai_generated: false,
  evidence: { skill_code: 'data_cleaning', job_evidence: [], course_evidence: [] },
})

describe('professional workflow presentation', () => {
  it('converts staged import states to visible result labels', () => {
    expect(importRowPresentation('duplicate')).toEqual({ color: 'orange', label: '重复' })
    expect(importRowPresentation('imported').label).toBe('已导入')
  })

  it('keeps the three curriculum coverage states distinct', () => {
    expect(coveragePresentation('covered').label).toBe('已覆盖')
    expect(coveragePresentation('partial').label).toBe('部分覆盖')
    expect(coveragePresentation('uncovered').label).toBe('未覆盖')
  })

  it('filters and transitions optimization suggestion decisions', () => {
    const items = [suggestion('1', 'pending'), suggestion('2', 'adopted')]
    expect(filterSuggestions(items, 'pending').map((item) => item.id)).toEqual(['1'])
    expect(nextSuggestionState('adopt')).toBe('adopted')
    expect(nextSuggestionState('ignore')).toBe('ignored')
  })
})
