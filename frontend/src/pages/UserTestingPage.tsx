import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import {
  completeUserTestSession,
  createUserTestSession,
  deleteUserTestSession,
  fetchUserTestReport,
  fetchUserTestScripts,
  fetchUserTestSessions,
  toErrorMessage,
  updateUserTestTask,
} from '@/services/api'
import type {
  UserTestOutcome,
  UserTestSession,
  UserTestTask,
} from '@/types/userTesting'

const { Title, Paragraph } = Typography

const ROLE_LABELS = { teacher: '教师', student: '学生' }
const OUTCOME_OPTIONS = [
  { value: 'completed', label: '完成' },
  { value: 'partial', label: '部分完成' },
  { value: 'failed', label: '未完成' },
]

function TaskObservationForm({ task, locked }: { task: UserTestTask; locked: boolean }) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm()
  const save = useMutation({
    mutationFn: (values: {
      actual_result: string
      outcome: UserTestOutcome
      accuracy: number
      ease_of_use: number
      feedback?: string
    }) => updateUserTestTask(task.id, values),
    onSuccess: () => {
      message.success('任务观察已保存')
      queryClient.invalidateQueries({ queryKey: ['user-testing-sessions'] })
      queryClient.invalidateQueries({ queryKey: ['user-testing-report'] })
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })

  return (
    <Card size="small" title={`${task.order_index + 1}. ${task.title}`}>
      <Paragraph type="secondary">预期结果：{task.expected_result}</Paragraph>
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          actual_result: task.actual_result,
          outcome: task.outcome,
          accuracy: task.accuracy,
          ease_of_use: task.ease_of_use,
          feedback: task.feedback,
        }}
        onFinish={save.mutate}
      >
        <Form.Item name="actual_result" label="实际结果" rules={[{ required: true, message: '请记录实际结果' }]}>
          <Input.TextArea rows={2} disabled={locked} placeholder="只记录观察到的实际结果，不要推测" />
        </Form.Item>
        <Row gutter={12}>
          <Col xs={24} md={8}>
            <Form.Item name="outcome" label="完成情况" rules={[{ required: true, message: '请选择完成情况' }]}>
              <Select disabled={locked} options={OUTCOME_OPTIONS} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item name="accuracy" label="预期达成度（1–5）" rules={[{ required: true, message: '请选择' }]}>
              <Select disabled={locked} options={[1, 2, 3, 4, 5].map((value) => ({ value, label: value }))} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item name="ease_of_use" label="易用性（1–5）" rules={[{ required: true, message: '请选择' }]}>
              <Select disabled={locked} options={[1, 2, 3, 4, 5].map((value) => ({ value, label: value }))} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="feedback" label="反馈（可选）">
          <Input.TextArea rows={2} disabled={locked} placeholder="例如：哪里不清晰、哪里最有帮助" />
        </Form.Item>
        {!locked && (
          <Button htmlType="submit" loading={save.isPending}>
            保存本项记录
          </Button>
        )}
      </Form>
    </Card>
  )
}

function SessionDetail({ session }: { session: UserTestSession }) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [feedback, setFeedback] = useState(session.overall_feedback ?? '')
  const complete = useMutation({
    mutationFn: () => completeUserTestSession(session.id, feedback),
    onSuccess: () => {
      message.success('用户测试会话已完成并计入报告')
      queryClient.invalidateQueries({ queryKey: ['user-testing-sessions'] })
      queryClient.invalidateQueries({ queryKey: ['user-testing-report'] })
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })
  const locked = session.status === 'completed'

  return (
    <Card title={`会话：${session.participant_alias}`}>
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          description="仅记录参与者别名、角色和知情同意；请勿在实际结果或反馈中写入姓名、联系方式、学号等个人信息。"
        />
        {session.tasks.map((task) => <TaskObservationForm key={task.id} task={task} locked={locked} />)}
        <Card size="small" title="整体反馈">
          <Input.TextArea
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            rows={3}
            disabled={locked}
            placeholder="可选：记录整体体验与改进建议"
          />
          {!locked && (
            <Button type="primary" style={{ marginTop: 12 }} loading={complete.isPending} onClick={() => complete.mutate()}>
              结束并纳入报告
            </Button>
          )}
        </Card>
      </Space>
    </Card>
  )
}

export function UserTestingPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState<string>()
  const [form] = Form.useForm()
  const scriptsQuery = useQuery({ queryKey: ['user-testing-scripts'], queryFn: fetchUserTestScripts })
  const sessionsQuery = useQuery({ queryKey: ['user-testing-sessions'], queryFn: fetchUserTestSessions })
  const reportQuery = useQuery({ queryKey: ['user-testing-report'], queryFn: fetchUserTestReport })
  const selectedSession = useMemo(
    () => sessionsQuery.data?.items.find((item) => item.id === selectedSessionId),
    [sessionsQuery.data, selectedSessionId],
  )
  const create = useMutation({
    mutationFn: (values: {
      participant_alias: string
      participant_role: 'teacher' | 'student'
      script_id: string
      consent_confirmed: boolean
    }) => createUserTestSession(values),
    onSuccess: (session) => {
      message.success('已创建匿名用户测试会话')
      setCreateOpen(false)
      form.resetFields()
      setSelectedSessionId(session.id)
      queryClient.invalidateQueries({ queryKey: ['user-testing-sessions'] })
      queryClient.invalidateQueries({ queryKey: ['user-testing-report'] })
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })
  const remove = useMutation({
    mutationFn: deleteUserTestSession,
    onSuccess: () => {
      message.success('用户测试数据已删除')
      setSelectedSessionId(undefined)
      queryClient.invalidateQueries({ queryKey: ['user-testing-sessions'] })
      queryClient.invalidateQueries({ queryKey: ['user-testing-report'] })
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })
  const report = reportQuery.data

  return (
    <Space orientation="vertical" size={20} style={{ width: '100%' }}>
      <div>
        <Title level={2}>真实用户测试</Title>
        <Paragraph type="secondary">使用统一脚本记录真实参与者的任务表现与反馈；报告只汇总已完成记录，不推断缺失数据。</Paragraph>
      </div>

      {report?.warnings.map((warning) => <Alert key={warning} type="warning" showIcon description={warning} />)}
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><Card><Statistic title="已完成会话" value={report?.completed_sessions ?? 0} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="任务完成率" value={report?.overall_completion_rate == null ? '—' : `${(report.overall_completion_rate * 100).toFixed(0)}%`} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="平均达成度" value={report?.average_accuracy ?? '—'} suffix={report?.average_accuracy == null ? undefined : '/ 5'} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="平均易用性" value={report?.average_ease_of_use ?? '—'} suffix={report?.average_ease_of_use == null ? undefined : '/ 5'} /></Card></Col>
      </Row>

      <Card
        title="测试会话"
        extra={<Button type="primary" onClick={() => setCreateOpen(true)}>新建匿名会话</Button>}
      >
        <Table
          rowKey="id"
          size="small"
          loading={sessionsQuery.isLoading}
          dataSource={sessionsQuery.data?.items ?? []}
          pagination={false}
          locale={{ emptyText: '尚无测试记录。邀请真实用户后，从“新建匿名会话”开始。' }}
          columns={[
            { title: '参与者别名', dataIndex: 'participant_alias' },
            { title: '角色', dataIndex: 'participant_role', render: (role: 'teacher' | 'student') => ROLE_LABELS[role] },
            { title: '状态', dataIndex: 'status', render: (status: string) => <Tag color={status === 'completed' ? 'green' : 'blue'}>{status === 'completed' ? '已完成' : '记录中'}</Tag> },
            { title: '任务数', render: (_: unknown, row: UserTestSession) => row.tasks.length },
            { title: '操作', render: (_: unknown, row: UserTestSession) => <Space><Button size="small" onClick={() => setSelectedSessionId(row.id)}>查看 / 记录</Button><Popconfirm title="删除该会话及全部测试记录？" onConfirm={() => remove.mutate(row.id)}><Button size="small" danger>删除</Button></Popconfirm></Space> },
          ]}
        />
      </Card>

      {selectedSession ? <SessionDetail session={selectedSession} /> : <Empty description="选择一条会话后可记录每个测试任务的实际结果" />}

      <Card title="汇总明细">
        {report?.tasks.length ? <Table rowKey="task_code" size="small" pagination={false} dataSource={report.tasks} columns={[{ title: '测试任务', dataIndex: 'title' }, { title: '记录数', dataIndex: 'response_count', width: 90 }, { title: '完成率', render: (_: unknown, row) => row.completion_rate == null ? '—' : `${(row.completion_rate * 100).toFixed(0)}%` }, { title: '达成度', dataIndex: 'average_accuracy', render: (value) => value == null ? '—' : `${value} / 5` }, { title: '易用性', dataIndex: 'average_ease_of_use', render: (value) => value == null ? '—' : `${value} / 5` }]} /> : <Empty description="完成真实用户测试后，这里才会显示汇总数据。" />}
        <Paragraph type="secondary" style={{ marginTop: 16 }}>{report?.reasoning_summary}</Paragraph>
      </Card>

      <Modal title="新建匿名用户测试会话" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending} okText="创建会话">
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} description="请仅填写化名（如“教师测试者01”），不要填写真实姓名、联系方式或学号。" />
        <Form form={form} layout="vertical" onFinish={create.mutate} initialValues={{ participant_role: 'teacher', consent_confirmed: false }}>
          <Form.Item name="participant_alias" label="参与者别名" rules={[{ required: true, message: '请输入匿名别名' }]}><Input /></Form.Item>
          <Form.Item name="participant_role" label="参与者角色" rules={[{ required: true }]}><Select options={[{ value: 'teacher', label: '教师' }, { value: 'student', label: '学生' }]} /></Form.Item>
          <Form.Item name="script_id" label="测试脚本" rules={[{ required: true, message: '请选择与角色匹配的脚本' }]}><Select loading={scriptsQuery.isLoading} options={scriptsQuery.data?.map((script) => ({ value: script.id, label: `${ROLE_LABELS[script.participant_role]} · ${script.name}` })) ?? []} /></Form.Item>
          <Form.Item name="consent_confirmed" valuePropName="checked" rules={[{ validator: (_, value) => value ? Promise.resolve() : Promise.reject(new Error('请先取得参与者的知情同意')) }]}>
            <Checkbox>我已向参与者说明测试目的、仅记录匿名别名与可随时删除记录，并已取得其知情同意。</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
