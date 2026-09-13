import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchOptimizationRun: vi.fn(), generateOptimization: vi.fn(), optimizationReportUrl: vi.fn(() => '/api/report.docx'), toErrorMessage: vi.fn(() => '请求失败'), updateOptimizationSuggestion: vi.fn(),
}))
vi.mock('@/services/api', () => api)
vi.mock('@/components/PageHero', () => ({ PageHero: ({ title }: { title: string }) => <h1>{title}</h1> }))
vi.mock('@/components/ProfessionalScopeBar', () => ({ ProfessionalScopeBar: () => <div>范围选择器</div> }))
vi.mock('@/hooks/useProfessionalScope', () => ({ useProfessionalScope: () => [{ jobId: 'job-1', planId: 'plan-1', graphId: 'graph-1' }, vi.fn()] }))

import { CurriculumOptimization } from './CurriculumOptimization'

const run = {
  id: 'run-1', job_id: 'job-1', plan_id: 'plan-1', graph_id: 'graph-1', status: 'active', low_sample: false, warnings: [],
  suggestions: [
    { id: 'suggestion-1', skill_code: 'skill-1', skill_name: '数据清洗', priority_score: 80, priority: 'high', action_type: 'add_course', title: '新增数据清洗课程', suggestion: '增加项目化数据清洗课程', state: 'pending', coverage_status: 'uncovered', posting_count: 36, affected_courses: [], generation_reason: '岗位频率高且未覆盖', ai_generated: true, evidence: { skill_code: 'skill-1', job_evidence: [], course_evidence: [] } },
    { id: 'suggestion-2', skill_code: 'skill-2', skill_name: '质量控制', priority_score: 55, priority: 'medium', action_type: 'adjust_hours', title: '调整质量控制课时', suggestion: '增加质检实训时间', state: 'adopted', coverage_status: 'partial', posting_count: 20, affected_courses: ['数据课程'], generation_reason: '部分覆盖', ai_generated: false, evidence: { skill_code: 'skill-2', job_evidence: [], course_evidence: [] } },
  ],
}
function renderPage() { return render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CurriculumOptimization /></QueryClientProvider></MemoryRouter>) }

describe('CurriculumOptimization', () => {
  beforeEach(() => { api.fetchOptimizationRun.mockResolvedValue(run); api.updateOptimizationSuggestion.mockResolvedValue(run.suggestions[0]) })

  it('filters, edits, adopts suggestions and exposes the DOCX report', async () => {
    renderPage()
    expect(await screen.findByText('新增数据清洗课程')).toBeVisible()
    const report = screen.getByRole('link', { name: '导出 DOCX 报告' })
    expect(report).toHaveAttribute('href', '/api/report.docx')

    fireEvent.click(document.querySelector('.ant-segmented-item-label[title="已采纳"]')!)
    expect(await screen.findByText('调整质量控制课时')).toBeVisible()
    expect(screen.queryByText('新增数据清洗课程')).not.toBeInTheDocument()

    fireEvent.click(document.querySelector('.ant-segmented-item-label[title="全部"]')!)
    await screen.findByText('新增数据清洗课程')
    expect(screen.getAllByRole('button', { name: '编辑' })[0]).toBeEnabled()
    fireEvent.click(screen.getAllByRole('button', { name: '采纳' })[0])
    await waitFor(() => expect(api.updateOptimizationSuggestion).toHaveBeenCalledWith('suggestion-1', { state: 'adopted' }))
  })
})
