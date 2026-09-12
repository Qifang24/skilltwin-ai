import { Alert, Button, Card, Descriptions, Space, Tag, Typography, Upload, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageHero } from '@/components/PageHero'
import { importJobPostings, toErrorMessage } from '@/services/api'
import type { JobPostingImportPayload, JobPostingImportResponse } from '@/types/jobMarket'

const { Dragger } = Upload
const { Paragraph, Text } = Typography

const TEMPLATE: JobPostingImportPayload = {
  job_id: 'ai_data_annotator',
  job_name: 'AI 数据标注工程师',
  postings: [{
    id: 'public-jd-20260911-001',
    title: 'AI 数据标注工程师',
    raw_text: '岗位职责：负责图像、文本等数据的标注、质检与问题反馈；熟悉标注规范和质量控制流程。任职要求：具备数据处理能力，能使用常见标注工具，工作细致负责。',
    source_name: '公开招聘来源名称',
    source_url: 'https://example.com/jobs/public-jd-20260911-001',
    posted_at: '2026-09-11T00:00:00+08:00',
    city: '北京',
    company_type: '互联网企业',
    data_flag: 'REAL',
  }],
}

function isImportPayload(value: unknown): value is JobPostingImportPayload {
  return Boolean(
    value
    && typeof value === 'object'
    && Array.isArray((value as JobPostingImportPayload).postings)
    && (value as JobPostingImportPayload).postings.length > 0,
  )
}

export function JobDataImportPage() {
  const navigate = useNavigate()
  const [payload, setPayload] = useState<JobPostingImportPayload | null>(null)
  const [fileName, setFileName] = useState('')
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<JobPostingImportResponse | null>(null)

  const downloadTemplate = () => {
    const blob = new Blob([JSON.stringify(TEMPLATE, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = '岗位数据导入模板.json'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const uploadProps: UploadProps = {
    accept: '.json,application/json',
    maxCount: 1,
    showUploadList: false,
    beforeUpload: async (file) => {
      try {
        const parsed: unknown = JSON.parse(await file.text())
        if (!isImportPayload(parsed)) throw new Error('文件需包含至少一条 postings 岗位记录')
        setPayload(parsed)
        setFileName(file.name)
        setResult(null)
        message.success(`已读取 ${parsed.postings.length} 条岗位记录`)
      } catch (error) {
        setPayload(null)
        setFileName('')
        message.error(error instanceof Error ? error.message : '无法读取 JSON 文件')
      }
      return false
    },
  }

  const submit = async () => {
    if (!payload) return
    setImporting(true)
    try {
      const nextResult = await importJobPostings(payload)
      setResult(nextResult)
      message.success('岗位数据已导入，技能需求统计已重建')
    } catch (error) {
      message.error(toErrorMessage(error))
    } finally {
      setImporting(false)
    }
  }

  return (
    <Space className="job-data-import-page" orientation="vertical" size={20} style={{ width: '100%' }}>
      <PageHero
        eyebrow="管理端 · 岗位数据治理"
        title="导入可追溯的岗位需求数据"
        description="将公开岗位 JD 导入系统，保留来源与原文证据，自动校验、去重、脱敏并更新岗位技能需求。"
        meta={<Tag color="cyan">单次最多导入 500 条岗位记录</Tag>}
        actions={<Button type="primary" onClick={() => navigate('/admin')}>{'\u2190 \u8fd4\u56de\u7ba1\u7406\u7aef'}</Button>}
      />

      <Card className="job-import-card" title="上传岗位数据" extra={<Button type="link" onClick={downloadTemplate}>下载 JSON 模板</Button>}>
        <Alert
          type="info"
          showIcon
          message="仅导入获得授权或公开可引用的岗位信息"
          description="每条 REAL 记录必须包含岗位原文、公开来源链接和发布日期。系统会移除文本中的手机号、邮箱和微信号，并跳过重复的岗位原文。"
        />
        <Dragger className="job-import-card__dropzone" {...uploadProps}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">拖入 JSON 文件，或点击选择文件</p>
          <p className="ant-upload-hint">请先下载模板并按字段填写；支持一个岗位及其同岗位族的多条 JD。</p>
        </Dragger>
        {payload ? (
          <div className="job-import-card__ready">
            <div><Text strong>{fileName}</Text><br /><Text type="secondary">已识别 {payload.postings.length} 条记录，目标岗位：{payload.job_name ?? 'AI 数据标注工程师'}</Text></div>
            <Button type="primary" size="large" loading={importing} onClick={submit}>校验并导入</Button>
          </div>
        ) : null}
      </Card>

      {result ? (
        <Card className="job-import-result" title="导入结果">
          <Descriptions column={{ xs: 2, md: 4 }}>
            <Descriptions.Item label="新增"><b>{result.created}</b> 条</Descriptions.Item>
            <Descriptions.Item label="更新"><b>{result.updated}</b> 条</Descriptions.Item>
            <Descriptions.Item label="重复跳过"><b>{result.skipped_duplicates}</b> 条</Descriptions.Item>
            <Descriptions.Item label="已脱敏"><b>{result.pii_scrubbed}</b> 条</Descriptions.Item>
          </Descriptions>
          <Paragraph type="secondary">当前统计已基于 {result.dashboard.data_quality.real_postings} 条真实岗位记录重建，可前往教师端「分析岗位需求」查看结果。</Paragraph>
        </Card>
      ) : null}
    </Space>
  )
}
