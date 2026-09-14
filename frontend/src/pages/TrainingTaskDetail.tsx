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
  Collapse,
  Descriptions,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Result,
  Row,
  Select,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { fetchTask, publishTask, refreshTaskCitations, toErrorMessage, updateTask } from '@/services/api'
import {
  DIFFICULTY_COLORS,
  DIFFICULTY_LABELS,
  TASK_STATUS_COLORS,
  TASK_STATUS_LABELS,
} from '@/types/training'

const COURSE_EVIDENCE_FIELD_LABELS: Record<string, string> = {
  source_quote: '课程原文',
  course_code: '课程代码',
  name: '课程名称',
  category: '课程类别',
  total_hours: '课程学时',
  objectives: '课程目标',
  description: '课程简介',
  teaching_content: '教学内容',
  knowledge_points: '知识点',
  practical_content: '实践内容',
  learning_outcomes: '学习成果',
  id: '课程记录编号',
}
import type { RubricDimension, TaskCourseEvidence } from '@/types/training'

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
  const [editOpen, setEditOpen] = useState(false)
  const [publisher, setPublisher] = useState('')
  const [editForm] = Form.useForm()
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

  const refreshCitations = useMutation({
    mutationFn: () => refreshTaskCitations(taskId),
    onSuccess: (task) => {
      message.success(task.citations.length ? `已补充 ${task.citations.length} 条知识库依据` : '未检索到匹配依据，请先导入相关资料')
      queryClient.invalidateQueries({ queryKey: ['task', taskId] })
    },
    onError: (err) => message.error(toErrorMessage(err)),
  })

  const saveTask = useMutation({
    mutationFn: async () => {
      const values = await editForm.validateFields()
      const parse = (value: string, label: string) => {
        try {
          return JSON.parse(value)
        } catch {
          throw new Error(`${label} 格式不正确，请检查 JSON 内容`)
        }
      }
      return updateTask(taskId, {
        title: values.title,
        scenario: values.scenario,
        difficulty: values.difficulty,
        est_minutes: values.est_minutes,
        safety_notes: values.safety_notes || null,
        objectives: parse(values.objectives, '学习目标'),
        deliverables: parse(values.deliverables, '提交成果'),
        steps: parse(values.steps, '任务步骤'),
        rubric: parse(values.rubric, '评分量规'),
        common_mistakes: parse(values.common_mistakes, '常见错误'),
        extensions: parse(values.extensions, '拓展任务'),
        skills: parse(values.skills, '训练技能与权重'),
      })
    },
    onSuccess: () => {
      message.success('任务内容已更新，学生端将显示最新版本')
      setEditOpen(false)
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

  const openEditor = () => {
    editForm.setFieldsValue({
      title: data.title,
      scenario: data.scenario,
      difficulty: data.difficulty,
      est_minutes: data.est_minutes,
      safety_notes: data.safety_notes,
      objectives: JSON.stringify(data.objectives, null, 2),
      deliverables: JSON.stringify(data.deliverables, null, 2),
      steps: JSON.stringify(data.steps, null, 2),
      rubric: JSON.stringify(data.rubric, null, 2),
      common_mistakes: JSON.stringify(data.common_mistakes, null, 2),
      extensions: JSON.stringify(data.extensions, null, 2),
      skills: JSON.stringify(data.skills.map(({ skill_code, weight, target_level }) => ({ skill_code, weight, target_level })), null, 2),
    })
    setEditOpen(true)
  }

  const rubricColumns = [
    {
      title: '评分维度',
      dataIndex: 'dimension',
      width: '24%',
      render: (value: string) => <Text strong>{value}</Text>,
    },
    {
      title: '权重',
      dataIndex: 'weight',
      width: '16%',
      render: (w: number) => <Text strong>{w}%</Text>,
    },
    {
      title: '评分标准',
      render: (_: unknown, row: RubricDimension) => (
        <Space orientation="vertical" size={4} style={{ width: '100%' }}>
          {row.levels.map((level) => (
            <div className="task-detail__rubric-level" key={level.level}>
              <Tag color={level.level === '优秀' ? 'cyan' : level.level === '合格' ? 'orange' : 'red'}>
                {level.level}
              </Tag>
              <Text strong style={{ fontSize: 13 }}>{level.criteria}</Text>
            </div>
          ))}
        </Space>
      ),
    },
  ]

  return (
    <Space className="task-detail" orientation="vertical" size={16} style={{ width: '100%' }}>
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
          {!isStudentView ? (
            <Button className="task-detail__edit-button" onClick={openEditor}>修改任务</Button>
          ) : selectedStudent ? (
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

      <Descriptions className="task-detail__summary" size="small" column={4} bordered>
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
        {data.curriculum_plan && <Descriptions.Item label="关联培养方案">{data.curriculum_plan.name}</Descriptions.Item>}
        {data.curriculum_course && <Descriptions.Item label="关联课程">{data.curriculum_course.name}</Descriptions.Item>}
      </Descriptions>

      {(data.curriculum_plan || data.curriculum_course) && (
        <Card className="task-detail-card task-detail-card--curriculum" title="课程依据" size="small">
          <Space orientation="vertical" size={8} style={{ width: '100%' }}>
            {data.curriculum_plan && <Text><Text type="secondary">培养方案：</Text>{data.curriculum_plan.name}{data.curriculum_plan.version ? ` · ${data.curriculum_plan.version}` : ''}</Text>}
            {data.curriculum_course && <>
              <Text><Text type="secondary">课程：</Text>{data.curriculum_course.name}{data.curriculum_course.total_hours ? ` · ${data.curriculum_course.total_hours} 学时` : ''}</Text>
              {data.curriculum_course.objectives && <Text type="secondary">课程目标：{data.curriculum_course.objectives}</Text>}
            </>}
            {(data.course_evidence ?? []).length > 0 ? <Collapse
              size="small"
              items={[{
                key: 'course-evidence',
                label: `查看生成时固化的 ${data.course_evidence?.length ?? 0} 条课程依据`,
                children: <List
                  size="small"
                  dataSource={data.course_evidence}
                  renderItem={(item: TaskCourseEvidence) => <List.Item>
                    <Space orientation="vertical" size={2} style={{ width: '100%' }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>{item.skill_code ? `课程—技能映射 · ${item.skill_code}` : item.field ? `课程材料 · ${COURSE_EVIDENCE_FIELD_LABELS[item.field] ?? item.field}` : '课程材料原文'}{item.page ? ` · 第${item.page}页` : ''}</Text>
                      <Text>“{item.quote}”</Text>
                    </Space>
                  </List.Item>}
                />,
              }]}
            /> : <Text type="secondary">已关联课程上下文；原始材料未提供可展示的连续引文。</Text>}
          </Space>
        </Card>
      )}

      <Card className="task-detail-card task-detail-card--scenario" title="工作情境" size="small">
        <Paragraph style={{ marginBottom: 0 }}>{data.scenario}</Paragraph>
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card className="task-detail-card task-detail-card--objectives" title="学习目标" size="small" style={{ height: '100%' }}>
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
          <Card className="task-detail-card task-detail-card--deliverables" title="提交成果" size="small" style={{ height: '100%' }}>
            <List
              size="small"
              dataSource={data.deliverables}
              renderItem={(item) => <List.Item>{item}</List.Item>}
            />
          </Card>
        </Col>
      </Row>

      <Card className="task-detail-card task-detail-card--steps" title="任务步骤" size="small">
        <div className="task-detail__steps-list">
          {data.steps.map((step) => (
            <div className="task-detail__step" key={step.order}>
              <Space className="task-detail__step-content" align="start" size={14}>
                <Tag className="task-detail__step-number" color="blue">{step.order}</Tag>
                <div className="task-detail__step-copy">
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
        </div>
      </Card>

      <Card className="task-detail-card task-detail-card--rubric" title="评分量规" size="small">
        <Table
          rowKey="dimension"
          size="small"
          bordered
          tableLayout="fixed"
          pagination={false}
          dataSource={data.rubric}
          columns={rubricColumns}
        />
      </Card>

      {data.common_mistakes.length > 0 && (
        <Card className="task-detail-card task-detail-card--mistakes" title="常见错误" size="small">
          <Space orientation="vertical" size={12} style={{ width: '100%' }}>
            {data.common_mistakes.map((item) => (
              <div
                key={item.mistake}
                className="task-detail__mistake"
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
          <Card className="task-detail-card task-detail-card--skills" title="训练技能与权重" size="small" style={{ height: '100%' }}>
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
          <Card
            className="task-detail-card task-detail-card--citations"
            title="设计依据"
            size="small"
            style={{ height: '100%' }}
            extra={
              !isStudentView && data.status === 'draft' ? (
                <Button size="small" loading={refreshCitations.isPending} onClick={() => refreshCitations.mutate()}>
                  重新检索知识库
                </Button>
              ) : null
            }
          >
            {data.citations.length === 0 ? (
              <div className="task-detail__citation-empty">
                <Text strong>暂无知识库依据</Text>
                <Text type="secondary">请先导入与本任务相关的职业标准、实训规范或课程资料；资料完成索引后，可点击“重新检索知识库”补充依据。</Text>
              </div>
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
              <Card className="task-detail-card task-detail-card--safety" title="安全与规范要求" size="small">
                <Paragraph style={{ marginBottom: 0 }}>{data.safety_notes}</Paragraph>
              </Card>
            </Col>
          )}
          {data.extensions.length > 0 && (
            <Col xs={24} lg={12}>
              <Card className="task-detail-card task-detail-card--extensions" title="拓展任务" size="small">
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

      {!isStudentView && data.status === 'draft' && (
        <Card className="task-detail-publish-card" size="small">
          <div>
            <strong>已完成任务内容核对？</strong>
            <Text type="secondary">发布后学生即可查看并开始完成本次实训任务。</Text>
          </div>
          <Button className="task-detail-publish-card__button" onClick={() => setPublishOpen(true)}>
            发布给学生 →
          </Button>
        </Card>
      )}

      <Modal
        title="修改实训任务"
        open={editOpen}
        onCancel={() => !saveTask.isPending && setEditOpen(false)}
        onOk={() => saveTask.mutate()}
        okText="保存全部修改"
        cancelText="取消"
        confirmLoading={saveTask.isPending}
        width={980}
      >
        <Form form={editForm} layout="vertical" className="task-edit-form">
          <Row gutter={14}>
            <Col xs={24} md={14}><Form.Item name="title" label="任务标题" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col xs={12} md={5}><Form.Item name="difficulty" label="难度" rules={[{ required: true }]}><Select options={Object.entries(DIFFICULTY_LABELS).map(([value, label]) => ({ value, label }))} /></Form.Item></Col>
            <Col xs={12} md={5}><Form.Item name="est_minutes" label="建议用时（分钟）" rules={[{ required: true }]}><InputNumber min={15} max={960} style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Form.Item name="scenario" label="工作情境" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="objectives" label="学习目标（JSON）" rules={[{ required: true }]}><Input.TextArea rows={7} /></Form.Item>
          <Form.Item name="deliverables" label="提交成果（JSON）" rules={[{ required: true }]}><Input.TextArea rows={5} /></Form.Item>
          <Form.Item name="steps" label="任务步骤（JSON）" rules={[{ required: true }]}><Input.TextArea rows={10} /></Form.Item>
          <Form.Item name="rubric" label="评分量规（JSON）" rules={[{ required: true }]}><Input.TextArea rows={10} /></Form.Item>
          <Form.Item name="common_mistakes" label="常见错误（JSON）"><Input.TextArea rows={7} /></Form.Item>
          <Form.Item name="skills" label="训练技能与权重（JSON）" rules={[{ required: true }]}><Input.TextArea rows={6} /></Form.Item>
          <Form.Item name="safety_notes" label="安全与规范要求"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="extensions" label="拓展任务（JSON）"><Input.TextArea rows={5} /></Form.Item>
        </Form>
      </Modal>

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
