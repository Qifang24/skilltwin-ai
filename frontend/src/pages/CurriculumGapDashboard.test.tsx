import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  confirmCurriculumImport: vi.fn(), createCourseSkillMapping: vi.fn(), createCurriculumAnalysis: vi.fn(), createCurriculumImport: vi.fn(), deleteCourseSkillMapping: vi.fn(), fetchCurriculumAnalysis: vi.fn(), fetchCurriculumPlan: vi.fn(), fetchSkillEvidence: vi.fn(), fetchSkills: vi.fn(), retryCurriculumImport: vi.fn(), toErrorMessage: vi.fn(() => '请求失败'), updateCourseSkillMapping: vi.fn(),
}))
const scope = vi.hoisted(() => ({ setScope: vi.fn() }))
vi.mock('@/services/api', () => api)
vi.mock('@/components/PageHero', () => ({ PageHero: ({ title }: { title: string }) => <h1>{title}</h1> }))
vi.mock('@/components/ProfessionalScopeBar', () => ({ ProfessionalScopeBar: () => <div>范围选择器</div> }))
vi.mock('@/hooks/useProfessionalScope', () => ({ useProfessionalScope: () => [{ jobId: 'job-1', planId: 'plan-1', graphId: 'graph-1' }, scope.setScope] }))

import { CurriculumGapDashboard } from './CurriculumGapDashboard'

const analysis = {
  id: 'analysis-1', job_id: 'job-1', plan_id: 'plan-1', graph_id: 'graph-1', warnings: [],
  metrics: { course_count: 1, mapped_skill_count: 3, covered: 1, partial: 1, uncovered: 1 },
  skills: [
    { skill_code: 'skill-covered', skill_name: '已覆盖技能', status: 'covered', demand_frequency: .6, courses: [{ id: 'map-1', course_id: 'course-1', course_name: '数据课程', skill_code: 'skill-covered', coverage_status: 'covered', origin: 'teacher', teacher_confirmed: true, evidence_quote: '课程覆盖原文' }] },
    { skill_code: 'skill-partial', skill_name: '部分覆盖技能', status: 'partial', demand_frequency: .4, courses: [] },
    { skill_code: 'skill-uncovered', skill_name: '未覆盖技能', status: 'uncovered', demand_frequency: .2, courses: [] },
  ],
}
function renderPage() { return render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CurriculumGapDashboard /></QueryClientProvider></MemoryRouter>) }

describe('CurriculumGapDashboard', () => {
  beforeEach(() => {
    api.fetchCurriculumAnalysis.mockResolvedValue(analysis)
    api.fetchCurriculumPlan.mockResolvedValue({ id: 'plan-1', name: '培养方案', courses: [{ id: 'course-1', name: '数据课程', total_hours: 32 }] })
    api.fetchSkills.mockResolvedValue({ items: [{ skill_code: 'skill-covered', name_zh: '已覆盖技能' }] })
    api.fetchSkillEvidence.mockResolvedValue({ skill_code: 'skill-covered', job_evidence: [{ title: '岗位 JD', quote: 'JD 原文' }], graph_evidence: { node_name: '能力节点', mastery_level: 3 }, course_evidence: [{ course_name: '数据课程', quote: '课程原文', page: '1', chunk_id: 'chunk-1' }] })
    api.createCourseSkillMapping.mockResolvedValue({})
    api.updateCourseSkillMapping.mockResolvedValue({})
  })

  it('renders all three coverage states, opens evidence, and exposes teacher mapping controls', async () => {
    renderPage()
    await screen.findByText('已覆盖技能')
    expect(screen.getAllByText('已覆盖').length).toBeGreaterThan(0)
    expect(screen.getAllByText('部分覆盖').length).toBeGreaterThan(0)
    expect(screen.getAllByText('未覆盖').length).toBeGreaterThan(0)

    fireEvent.click(screen.getAllByRole('button', { name: '查看' })[0])
    expect(await screen.findByText('JD → 技能 → 图谱 → 课程原文')).toBeVisible()
    await waitFor(() => expect(api.fetchSkillEvidence).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByText('JD · 岗位 JD')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '课程视图' }))
    expect(screen.getByText('添加映射')).toBeInTheDocument()
  })

  it('offers a start-analysis action when the selected scope has no analysis yet', async () => {
    api.fetchCurriculumAnalysis.mockRejectedValueOnce(new Error('analysis not found'))
    api.createCurriculumAnalysis.mockResolvedValue(analysis)
    renderPage()

    expect(await screen.findByText('尚未创建课程对标分析')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '开始对标分析' }))
    await waitFor(() => expect(api.createCurriculumAnalysis).toHaveBeenCalledWith({ job_id: 'job-1', plan_id: 'plan-1', graph_id: 'graph-1' }))
  })
})
