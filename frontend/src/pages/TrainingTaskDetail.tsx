/**
 * 实训任务详情页。
 *
 * 按区块渲染而非一整篇 Markdown —— 教师上课时要能单独看步骤或量规，
 * 学生做任务时要能对着步骤逐条推进。结构化的价值在这里才兑现。
 */

import {
  Alert,
  App,
  Breadcrumb,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  List,
  Modal,
  Result,
  Row,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { fetchTask, publishTask, toErrorMessage } from '@/services/api'
import {
  DIFFICULTY_COLORS,
  DIFFICULTY_LABELS,
  TASK_STATUS_COLORS,
  TASK_STATUS_LABELS,
} from '@/types/training'
import type { RubricDimension } from '@/types/training'

const { Title, Paragraph, Text } = Typography

interface TrainingTaskDetailProps {
  audience?: 'teacher' | 'student'
}

export function TrainingTaskDetail({ audience = 'teacher' }: TrainingTaskDetailProps) {
  const { taskId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [publishOpen, setPublishOpen] = useState(false)
  const [publisher, setPublisher] = useState('')
  const isStudentView = audience === 'student'
  const selectedStudent = searchParams.get('student')
  const backPath = isStudentView
    ? `/student${selectedStudent ? `?student=${encodeURIComponent(selectedStudent)}` : ''}`
    : '/teacher'
  const backLabel = isStudentView ? '返回学习中心' : '返回工作台'

  const { data, isLoading, error } = useQuery({
    queryKey: ['task', taskId],
    queryFn: () => fetchTask(taskId),
    enabled: Boolean(taskId),
  })

  const publish = useMutation({
    mutationFn: () => publishTask(taskId, publisher.trim()),
    onSuccess: () => {
      message.success('任务已发布')
      setPublishOpen(false)
      queryClient.invalidateQueries({ queryKey: ['task', taskId] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: (err) => message.error(toErrorMessage(err)),
  })

  if (isLoading) return <Skeleton active paragraph={{ rows: 12 }} />
  if (error || !data) {
    return (
      <Result
        status="error"
        title="无法加载任务"
        subTitle={toErrorMessage(error)}
        extra={
          <Link to={backPath}>
            <Button type="primary">{backLabel}</Button>
          </Link>
        }
      />
    )
  }

  const weightTotal = data.rubric.reduce((sum, d) => sum + d.weight, 0)

  const rubricColumns = [
    { title: '评分维度', dataIndex: 'dimension', width: 140 },
    {
      title: '权重',
      dataIndex: 'weight',
      width: 80,
      render: (w: number) => `${w}%`,
    },
    {
      title: '评分标准',
      render: (_: unknown, row: RubricDimension) => (
        <Space orientation="vertical" size={4} style={{ width: '100%' }}>
          {row.levels.map((level) => (
            <div key={level.level}>
              <Tag>{level.level}</Tag>
              <Text style={{ fontSize: 13 }}>{level.criteria}</Text>
            </div>
          ))}
        </Space>
      ),
    },
  ]

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Breadcrumb
        items={[
          {
            title: (
              <Link to={backPath}>
                {isStudentView ? '学生学习中心' : '教师工作台'}
              </Link>
            ),
          },
          { title: data.title },
        ]}
      />

      <Row justify="space-between" align="middle" gutter={[16, 16]}>
        <Col>
          <Space align="center" size={12} wrap>
            <Title level={3} style={{ margin: 0 }}>
              {data.title}
            </Title>
            <Tag color={DIFFICULTY_COLORS[data.difficulty]}>
              {DIFFICULTY_LABELS[data.difficulty]}
            </Tag>
            <Tag color={TASK_STATUS_COLORS[data.status]}>
              {TASK_STATUS_LABELS[data.status]}
            </Tag>
            {data.ai_generated && <Tag color="blue">AI 生成</Tag>}
          </Space>
        </Col>
        <Col>
          {!isStudentView && data.status === 'draft' ? (
            <Button type="primary" onClick={() => setPublishOpen(true)}>
              发布给学生
            </Button>
          ) : isStudentView && selectedStudent ? (
            <Link to={`/student/tutor?student=${encodeURIComponent(selectedStudent)}&task=${encodeURIComponent(taskId)}`}>
              <Button type="primary">向 AI Tutor 提问</Button>
            </Link>
          ) : (
            <Text type="secondary">
              {data.status === 'published'
                ? '已发布实训任务'
                : data.published_by
                  ? `已由 ${data.published_by} 发布`
                  : '已归档'}
            </Text>
          )}
        </Col>
      </Row>

      {data.warnings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          title="生成提示"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {data.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          }
        />
      )}

      <Descriptions size="small" column={4} bordered>
        <Descriptions.Item label="派生自">
          {data.source_node_name ?? '—'}
        </Descriptions.Item>
        <Descriptions.Item label="建议用时">
          {data.est_minutes ? `${data.est_minutes} 分钟` : '—'}
        </Descriptions.Item>
        <Descriptions.Item label="训练技能">{data.skill_count} 项</Descriptions.Item>
        <Descriptions.Item label="量规权重">
          {weightTotal === 100 ? (
            '100%'
          ) : (
            <Text type="warning">{weightTotal}%（通常应为 100）</Text>
          )}
        </Descriptions.Item>
      </Descriptions>

      <Card title="工作情境" size="small">
        <Paragraph style={{ marginBottom: 0 }}>{data.scenario}</Paragraph>
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card title="学习目标" size="small" style={{ height: '100%' }}>
            <List
              size="small"
              dataSource={data.objectives}
              renderItem={(item) => (
                <List.Item>
                  <Space size={8} wrap>
                    <Text>{item.text}</Text>
                    {item.skill_code && (
                      <Tag color="magenta" style={{ fontSize: 11 }}>
                        {item.skill_code}
                      </Tag>
                    )}
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="提交成果" size="small" style={{ height: '100%' }}>
            <List
              size="small"
              dataSource={data.deliverables}
              renderItem={(item) => <List.Item>{item}</List.Item>}
            />
          </Card>
        </Col>
      </Row>

      <Card title="任务步骤" size="small">
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          {data.steps.map((step) => (
            <div key={step.order}>
              <Space align="start" size={10}>
                <Tag color="blue">{step.order}</Tag>
                <div>
                  <Text strong>{step.title}</Text>
                  <Paragraph style={{ marginTop: 4, marginBottom: 4 }}>
                    {step.detail}
                  </Paragraph>
                  {step.hint && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      💡 提示：{step.hint}
                    </Text>
                  )}
                </div>
              </Space>
            </div>
          ))}
        </Space>
      </Card>

      <Card title="评分量规" size="small">
        <Table
          rowKey="dimension"
          size="small"
          pagination={false}
          dataSource={data.rubric}
          columns={rubricColumns}
        />
      </Card>

      {data.common_mistakes.length > 0 && (
        <Card title="常见错误" size="small">
          <Space orientation="vertical" size={12} style={{ width: '100%' }}>
            {data.common_mistakes.map((item) => (
              <div
                key={item.mistake}
                style={{
                  borderLeft: '3px solid #ff4d4f',
                  padding: '8px 12px',
                  background: 'rgba(255,77,79,0.04)',
                  borderRadius: 4,
                }}
              >
                <Text strong>{item.mistake}</Text>
                <div style={{ fontSize: 13, marginTop: 4 }}>
                  <Text type="secondary">后果：</Text>
                  {item.consequence}
                </div>
                <div style={{ fontSize: 13 }}>
                  <Text type="secondary">纠正：</Text>
                  {item.fix}
                </div>
              </div>
            ))}
          </Space>
        </Card>
      )}

      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card title="训练技能与权重" size="small" style={{ height: '100%' }}>
            <List
              size="small"
              dataSource={data.skills}
              renderItem={(item) => (
                <List.Item>
                  <Space size={8} wrap>
                    <Tag color="magenta">{item.skill_code}</Tag>
                    <Text>{item.skill_name}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      权重 {(item.weight * 100).toFixed(0)}%
                      {item.target_level ? ` · 目标 L${item.target_level}` : ''}
                    </Text>
                  </Space>
                </List.Item>
              )}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              学生完成后，评分将按此权重回写到对应技能的能力画像。
            </Text>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="设计依据" size="small" style={{ height: '100%' }}>
            {data.citations.length === 0 ? (
              <Text type="secondary">本任务未检索到知识库依据，建议核实后再发布。</Text>
            ) : (
              <Space orientation="vertical" size={10} style={{ width: '100%' }}>
                {data.citations.slice(0, 4).map((c, index) => (
                  <div key={`${c.chunk_id}-${index}`}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {[c.source_name, c.section, c.page ? `第${c.page}页` : null]
                        .filter(Boolean)
                        .join(' · ')}
                    </Text>
                    <Paragraph
                      style={{ fontSize: 13, marginBottom: 0, marginTop: 2 }}
                      ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                    >
                      {c.quote}
                    </Paragraph>
                  </div>
                ))}
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      {(data.safety_notes || data.extensions.length > 0) && (
        <Row gutter={16}>
          {data.safety_notes && (
            <Col xs={24} lg={12}>
              <Card title="安全与规范要求" size="small">
                <Paragraph style={{ marginBottom: 0 }}>{data.safety_notes}</Paragraph>
              </Card>
            </Col>
          )}
          {data.extensions.length > 0 && (
            <Col xs={24} lg={12}>
              <Card title="拓展任务" size="small">
                <List
                  size="small"
                  dataSource={data.extensions}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />
              </Card>
            </Col>
          )}
        </Row>
      )}

      <Modal
        title="发布任务"
        open={publishOpen}
        onCancel={() => setPublishOpen(false)}
        onOk={() => publish.mutate()}
        okText="确认发布"
        cancelText="取消"
        confirmLoading={publish.isPending}
        okButtonProps={{ disabled: !publisher.trim() }}
      >
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            发布后学生可见。请确认任务步骤与评分标准无误 —— 这份内容由 AI
            生成，需要你把关后再交给学生。
          </Paragraph>
          <Input
            placeholder="请输入发布人姓名"
            value={publisher}
            onChange={(e) => setPublisher(e.target.value)}
            onPressEnter={() => publisher.trim() && publish.mutate()}
          />
        </Space>
      </Modal>
    </Space>
  )
}
