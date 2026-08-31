import { Alert, Button, Card, Empty, Input, Select, Space, Typography } from 'antd'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { fetchTasks, sendTutorMessage, toErrorMessage } from '@/services/api'
import type { EvidenceSufficiency, SourceRef } from '@/types/api'

const { Title, Paragraph, Text } = Typography
const JOB_ID = 'ai_data_annotator'

type ChatLine = {
  role: 'user' | 'assistant'
  content: string
  sources?: SourceRef[]
  warnings?: string[]
  evidenceSufficiency?: EvidenceSufficiency
}

function EvidenceBlock({ line }: { line: ChatLine }) {
  if (line.role !== 'assistant') return null

  return (
    <Space orientation="vertical" size={6} style={{ width: '100%' }}>
      {line.evidenceSufficiency && (
        <Text type="secondary">
          证据状态：
          {line.evidenceSufficiency === 'sufficient'
            ? '已核验'
            : line.evidenceSufficiency === 'partial'
              ? '部分核验'
              : '证据不足'}
        </Text>
      )}
      {line.sources?.map((source) => (
        <Text key={`${source.type}-${source.chunk_id ?? source.posting_id}`} type="secondary">
          【依据】{source.source_name ?? source.marker ?? '知识库'}
          {source.page ? ` · 第${source.page}页` : ''}
          {source.quote ? `：${source.quote}` : ''}
        </Text>
      ))}
      {line.warnings?.map((warning) => (
        <Alert key={warning} type="warning" showIcon description={warning} />
      ))}
    </Space>
  )
}

export function TutorPage() {
  const [params] = useSearchParams()
  const studentId = params.get('student')
  const taskId = params.get('task') ?? undefined
  const [text, setText] = useState('')
  const [conversationId, setConversationId] = useState<string>()
  const [selectedTaskId, setSelectedTaskId] = useState(taskId)
  const [lines, setLines] = useState<ChatLine[]>([])

  const tasks = useQuery({
    queryKey: ['tutor-tasks', JOB_ID],
    queryFn: () => fetchTasks({ job_id: JOB_ID, status: 'published' }),
  })
  const chat = useMutation({
    mutationFn: (message: string) =>
      sendTutorMessage(studentId!, {
        message,
        job_id: JOB_ID,
        task_id: selectedTaskId,
        conversation_id: conversationId,
      }),
    onSuccess: (reply) => {
      setConversationId(reply.conversation_id)
      setLines((previous) => [
        ...previous,
        {
          role: 'assistant',
          content: reply.answer.content,
          sources: reply.answer.sources,
          warnings: reply.warnings,
          evidenceSufficiency: reply.evidence_sufficiency,
        },
      ])
    },
  })

  const send = () => {
    const message = text.trim()
    if (!message || chat.isPending) return
    setText('')
    setLines((previous) => [...previous, { role: 'user', content: message }])
    chat.mutate(message)
  }

  if (!studentId) {
    return <Empty description="请先从学生学习中心选择学生后再使用 AI Tutor" />
  }

  return (
    <Space orientation="vertical" size={20} style={{ width: '100%' }}>
      <div>
        <Title level={2}>AI 学习助手</Title>
        <Paragraph type="secondary">
          回答结合你的能力画像、当前实训任务、最近对话与知识库依据。AI 生成内容请结合教师指导核验。
        </Paragraph>
      </div>

      <Card size="small" title="当前实训任务（可选）">
        <Select
          allowClear
          loading={tasks.isLoading}
          value={selectedTaskId}
          onChange={(value) => {
            setSelectedTaskId(value)
            setConversationId(undefined)
            setLines([])
          }}
          placeholder="选择任务，让 Tutor 给出情境化指导"
          style={{ width: '100%' }}
          options={tasks.data?.items.map((task) => ({ value: task.id, label: task.title })) ?? []}
        />
      </Card>

      {chat.isError ? (
        <Alert
          type="error"
          showIcon
          title="Tutor 暂时不可用"
          description={toErrorMessage(chat.error)}
        />
      ) : null}

      <Card>
        {lines.length ? (
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            {lines.map((line, index) => (
              <div key={`${line.role}-${index}`}>
                <Text strong>{line.role === 'user' ? '我' : 'AI Tutor'}</Text>
                <Paragraph style={{ whiteSpace: 'pre-wrap', margin: '4px 0' }}>
                  {line.content}
                </Paragraph>
                <EvidenceBlock line={line} />
              </div>
            ))}
          </Space>
        ) : (
          <Empty description="例如：这一步的数据清洗要怎么做？" />
        )}
      </Card>

      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={text}
          onChange={(event) => setText(event.target.value)}
          onPressEnter={send}
          placeholder="输入你的问题…"
          disabled={chat.isPending}
        />
        <Button type="primary" loading={chat.isPending} onClick={send}>
          发送
        </Button>
      </Space.Compact>
    </Space>
  )
}
