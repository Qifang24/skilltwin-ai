import { App as AntApp } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchCurriculumPlan: vi.fn(), fetchCurriculumPlans: vi.fn(), fetchGraph: vi.fn(), fetchGraphs: vi.fn(), fetchTasks: vi.fn(), generateTask: vi.fn(), toErrorMessage: vi.fn(() => '请求失败'),
}))
vi.mock('@/services/api', () => api)
vi.mock('@/components/PageHero', () => ({ PageHero: ({ title }: { title: string }) => <h1>{title}</h1> }))

import { TrainingTaskLibrary } from './TrainingTaskLibrary'

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/teacher/tasks?graph_id=graph-1&node_id=unit-1&plan_id=plan-1&course_id=course-1']}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <AntApp><TrainingTaskLibrary /></AntApp>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('TrainingTaskLibrary curriculum link', () => {
  beforeEach(() => {
    api.fetchTasks.mockResolvedValue({ items: [{ id: 'task-1', title: '已有任务', difficulty: 'beginner', status: 'draft', skill_count: 1, course_id: 'course-1' }], total: 1 })
    api.fetchGraphs.mockResolvedValue({ items: [{ id: 'graph-1', status: 'approved' }] })
    api.fetchGraph.mockResolvedValue({ tree: [{ id: 'unit-1', name: '数据标注能力', node_type: 'competency_unit', children: [] }] })
    api.fetchCurriculumPlans.mockResolvedValue([{ id: 'plan-1', name: 'AI 技术应用培养方案' }])
    api.fetchCurriculumPlan.mockResolvedValue({ id: 'plan-1', name: 'AI 技术应用培养方案', courses: [{ id: 'course-1', name: '数据标注实训', total_hours: 32 }] })
    api.generateTask.mockResolvedValue({ id: 'task-new' })
  })

  it('uses curriculum selections carried from the course view when generating a task', async () => {
    renderPage()
    expect(await screen.findByText('数据标注实训 · 32 学时')).toBeInTheDocument()
    const generate = screen.getByRole('button', { name: '生成实训任务 →' })
    await waitFor(() => expect(generate).toBeEnabled())
    fireEvent.click(generate)
    await waitFor(() => expect(api.generateTask).toHaveBeenCalledWith('unit-1', 'beginner', undefined, { planId: 'plan-1', courseId: 'course-1' }))
    expect(screen.getByText('已关联课程')).toBeInTheDocument()
  })
})
