import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { JobImportBatch, JobImportResult } from '@/types/professional'

const api = vi.hoisted(() => ({
  confirmJobImport: vi.fn(), createJobImport: vi.fn(), fetchJobImportPreview: vi.fn(),
  toErrorMessage: vi.fn(() => '请求失败'), updateJobImportMapping: vi.fn(),
}))
vi.mock('@/services/api', () => api)
vi.mock('@/components/PageHero', () => ({ PageHero: ({ title }: { title: string }) => <h1>{title}</h1> }))

import { JobDataImportPage } from './JobDataImportPage'

const batch: JobImportBatch = {
  id: 'batch-1', job_id: 'job-1', job_name: '岗位', status: 'validated', total_rows: 1,
  headers: ['title', 'raw_text', 'source_name'],
  mapping: { title: 'title', raw_text: 'raw_text', source_name: 'source_name' },
  rows: [{ row_number: 1, state: 'valid', data: { title: '数据标注师', raw_text: '负责数据标注', source_name: '招聘网' }, issues: [] }],
}
const duplicateBatch: JobImportBatch = {
  ...batch,
  status: 'validated',
  rows: [{ row_number: 1, state: 'duplicate', data: { title: '数据标注师', raw_text: '负责数据标注', source_name: '招聘网' }, issues: [{ message: '与批内或历史岗位正文重复' }] }],
  preview_rows: [{ row_number: 1, state: 'duplicate', data: { title: '数据标注师', raw_text: '负责数据标注', source_name: '招聘网' }, issues: [{ message: '与批内或历史岗位正文重复' }] }],
}
const result: JobImportResult = { batch_id: 'batch-1', job_id: 'job-1', created: 1, updated: 0, skipped_duplicates: 0, filtered: 0, failed: 0, pii_scrubbed: 0, rows: [], warnings: [] }
function renderPage() { return render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><JobDataImportPage /></QueryClientProvider></MemoryRouter>) }

describe('JobDataImportPage', () => {
  beforeEach(() => { api.createJobImport.mockResolvedValue(batch); api.updateJobImportMapping.mockResolvedValue(batch); api.fetchJobImportPreview.mockResolvedValue(batch); api.confirmJobImport.mockResolvedValue(result) })

  it('shows the four staged steps and does not write formal postings before confirmation', async () => {
    renderPage()
    for (const title of ['上传文件', '字段映射', '预览校验', '导入结果']) expect(screen.getByText(title)).toBeVisible()
    expect(api.confirmJobImport).not.toHaveBeenCalled()

    const file = new File(['title,raw_text,source_name\n数据标注师,负责数据标注,招聘网'], 'jobs.csv', { type: 'text/csv' })
    const fileInput = document.querySelector('input[type="file"]')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput!, { target: { files: [file] } })
    await screen.findByText('2. 字段映射')
    expect(api.confirmJobImport).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '保存并校验' }))
    await screen.findByText('3. 预览、校验与去重')
    expect(api.confirmJobImport).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '确认导入' }))
    await waitFor(() => expect(api.confirmJobImport).toHaveBeenCalledWith('batch-1'))
    expect(await screen.findByText('4. 导入结果')).toBeVisible()
  })

  it('downloads the CSV template with a UTF-8 BOM for Excel compatibility', async () => {
    const createObjectURL = vi.fn((_object: Blob) => 'blob:template')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    try {
      renderPage()
      fireEvent.click(screen.getByRole('button', { name: '下载 CSV 模板' }))
      const blob = createObjectURL.mock.calls[0][0] as Blob
      const bytes = new Uint8Array(await blob.arrayBuffer())
      expect(Array.from(bytes.slice(0, 3))).toEqual([0xef, 0xbb, 0xbf])
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:template')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('explains an all-duplicate batch and disables confirmation', async () => {
    api.createJobImport.mockResolvedValueOnce(duplicateBatch)
    api.updateJobImportMapping.mockResolvedValueOnce(duplicateBatch)
    api.fetchJobImportPreview.mockResolvedValueOnce(duplicateBatch)
    renderPage()
    const file = new File(['title,raw_text,source_name\n数据标注师,负责数据标注,招聘网'], 'duplicate.csv', { type: 'text/csv' })
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } })
    await screen.findByText('2. 字段映射')
    fireEvent.click(screen.getByRole('button', { name: '保存并校验' }))
    await screen.findByText('3. 预览、校验与去重')
    expect(await screen.findByText('本批次没有可导入记录')).toBeVisible()
    expect(screen.getByRole('button', { name: '确认导入' })).toBeDisabled()
    expect(api.confirmJobImport).not.toHaveBeenCalled()
  })
})
