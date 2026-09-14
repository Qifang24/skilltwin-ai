/**
 * 学生学习中心：选学生 → 看能力画像 → 看差距 → 去测评。
 *
 * 演示期用「选择学生」代替登录 —— 本项目不做认证（见 v0.1 范围），
 * 学生数据全部化名。
 */

import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  Modal,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { SkillIntervalChart } from '@/charts/SkillIntervalChart'
import { SkillRadar } from '@/charts/SkillRadar'
import { PageHero } from '@/components/PageHero'
import {
  createStudent,
  fetchGap,
  fetchProfile,
  fetchStudents,
  fetchTasks,
  startAssessment,
  toErrorMessage,
} from '@/services/api'
import type { SkillGap } from '@/types/student'
import { DIFFICULTY_COLORS, DIFFICULTY_LABELS, type TrainingTaskSummary } from '@/types/training'

const { Title, Paragraph, Text } = Typography

const TARGET_JOB = 'ai_data_annotator'

export function StudentDashboard() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const studentId = searchParams.get('student')
  const isDiagnosisPage = location.pathname === '/student/diagnosis'
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [diagnosticHint, setDiagnosticHint] = useState<string | null>(null)

  const studentsQuery = useQuery({ queryKey: ['students'], queryFn: fetchStudents })
  const publishedTasksQuery = useQuery({
    queryKey: ['student-published-tasks', TARGET_JOB],
    queryFn: () => fetchTasks({ job_id: TARGET_JOB, status: 'published' }),
  })

  const profileQuery = useQuery({
    queryKey: ['profile', studentId, TARGET_JOB],
    queryFn: () => fetchProfile(studentId!, TARGET_JOB),
    enabled: Boolean(studentId),
    retry: false,
  })

  const gapQuery = useQuery({
    queryKey: ['gap', studentId, TARGET_JOB],
    queryFn: () => fetchGap(studentId!, TARGET_JOB),
    enabled: Boolean(studentId),
    retry: false,
  })

  const create = useMutation({
    mutationFn: () =>
      createStudent({ display_name: newName.trim(), target_job_id: TARGET_JOB }),
    onSuccess: (student) => {
      message.success('已创建')
      setCreateOpen(false)
      setNewName('')
      setSearchParams({ student: student.id })
      queryClient.invalidateQueries({ queryKey: ['students'] })
    },
    onError: (e) => message.error(toErrorMessage(e)),
  })

  const startDiagnostic = useMutation({
    mutationFn: () => startAssessment(studentId!, TARGET_JOB, 16, 'diagnostic'),
    onSuccess: (assessment) => navigate(`/student/assessments/${assessment.id}`),
    onError: (e) => {
      const detail = toErrorMessage(e)
      setDiagnosticHint('暂时无法开始诊断。通常是教师尚未准备好题库，请联系教师确认后再试。')
      message.error(detail)
    },
  })

  const gaps = gapQuery.data?.gaps ?? []
  const profile = profileQuery.data
  const hasDiagnosticResult = gaps.some((gap) => !gap.untested)
  const targets: Record<string, number> = Object.fromEntries(
    gaps.map((g) => [g.skill_code, g.target_score]),
  )

  const gapColumns = [
    {
      title: '技能',
      dataIndex: 'skill_name',
      width: 210,
      render: (name: string | null, row: SkillGap) => name ?? row.skill_code,
    },
    {
      title: '岗位目标',
      dataIndex: 'target_score',
      width: 100,
      render: (v: number) => v.toFixed(0),
    },
    {
      title: '当前水平',
      dataIndex: 'current_score',
      width: 120,
      render: (v: number, row: SkillGap) =>
        row.untested ? <Text type="secondary">尚未测评</Text> : v.toFixed(1),
    },
    {
      title: '差距',
      dataIndex: 'gap',
      width: 100,
      render: (v: number, row: SkillGap) =>
        row.untested ? (
          <Text strong type="secondary">—</Text>
        ) : (
          <Text strong type={v > 20 ? 'danger' : v > 0 ? 'warning' : 'success'}>
            {v > 0 ? `落后 ${v.toFixed(1)}` : '已达标'}
          </Text>
        ),
    },
    {
      title: '证据',
      dataIndex: 'evidence_count',
      width: 140,
      render: (n: number, row: SkillGap) =>
        row.untested ? (
          <Tag>未考查</Tag>
        ) : (
          <Space size={4}>
            <Text style={{ fontSize: 12 }}>{n} 题</Text>
            {!row.reliable && <Tag color="orange" className="student-evidence-tag">证据不足</Tag>}
          </Space>
        ),
    },
  ]

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <Space className="student-workspace" orientation="vertical" size={14} style={{ width: '100%' }}>
      {isDiagnosisPage ? (
        <PageHero
          eyebrow="STEP 02 · 能力诊断"
          title="完成能力诊断，查看你的能力画像"
          description="先完成诊断测评；完成后可在本页查看能力雷达图、能力区间和技能差距。"
          actions={<Button type="primary" onClick={() => navigate(`/student?student=${encodeURIComponent(studentId ?? '')}`)}>← 返回上一步</Button>}
        />
      ) : (
      <PageHero
        eyebrow="学生学习中心 · 个性化成长"
        title="从能力诊断到个性化学习"
        description="选择学习档案，完成能力诊断，按系统生成的学习路径练习与复测。"
        meta={<Space wrap><Tag color="blue">目标岗位 · AI 数据标注工程师</Tag><Tag color="cyan">能力画像会随测评和实训更新</Tag></Space>}
      />
      )}

      {!isDiagnosisPage && <>
      <Card className="student-workflow-card" title="三步开始个性化学习" extra={<Text type="secondary">诊断结果决定你的学习重点和练习顺序</Text>}>
        <Row gutter={[12, 12]}>
          <Col xs={24} md={8}>
            <Card id="student-profile-selector" size="small" className="student-workflow-step student-workflow-step--01">
              <span className="student-workflow-step__number">STEP 01</span>
              <Title level={5}>选择学习档案</Title>
              <Paragraph>选择已有化名，或新建一个学习档案。</Paragraph>
              <div className="student-workflow-step__profile">
                <Select
                  placeholder="选择一个学生（演示用，无需登录）"
                  value={studentId}
                  onChange={(value) => {
                    setDiagnosticHint(null)
                    setSearchParams({ student: value })
                  }}
                  loading={studentsQuery.isLoading}
                  options={(studentsQuery.data ?? []).map((s) => ({
                    value: s.id,
                    label: `${s.display_name}（${s.id.slice(0, 12)}）`,
                  }))}
                />
                <Button onClick={() => setCreateOpen(true)}>新建学生</Button>
              </div>
              <Text className="student-workflow-step__hint">仅保存化名，不记录姓名、学号等个人信息。</Text>
            </Card>
          </Col>
          <Col xs={24} md={8}>
            <Card size="small" className="student-workflow-step student-workflow-step--02">
              <span className="student-workflow-step__number">STEP 02</span>
              <Title level={5}>完成能力诊断</Title>
              <Paragraph>通过诊断题生成能力画像，查看与岗位要求的差距。</Paragraph>
              <Button disabled={!studentId} onClick={() => studentId ? navigate(`/student/diagnosis?student=${encodeURIComponent(studentId)}`) : scrollTo('student-profile-selector')}>{studentId ? (hasDiagnosticResult ? '查看能力诊断结果 →' : '开始能力诊断 →') : '先选择学习档案 →'}</Button>
            </Card>
          </Col>
          <Col xs={24} md={8}>
            <Card id="student-step-03" size="small" className="student-workflow-step student-workflow-step--03">
              <span className="student-workflow-step__number">STEP 03</span>
              <Title level={5}>按路径练习</Title>
              <Paragraph>按优先顺序完成练习与实训，并在需要时参加复测。</Paragraph>
              <Button disabled={!studentId} onClick={() => studentId ? (hasDiagnosticResult ? navigate(`/student/path?student=${encodeURIComponent(studentId)}`) : navigate(`/student/diagnosis?student=${encodeURIComponent(studentId)}`)) : scrollTo('student-profile-selector')}>{hasDiagnosticResult ? '查看学习路径 →' : studentId ? '先完成能力诊断 →' : '先选择学习档案 →'}</Button>
            </Card>
          </Col>
        </Row>
      </Card>

      <Card
        className="student-published-tasks-card"
        title="已发布实训任务"
        extra={<Text type="secondary">{publishedTasksQuery.data?.total ?? 0} 项任务可开始</Text>}
      >
        <List
          loading={publishedTasksQuery.isLoading}
          dataSource={publishedTasksQuery.data?.items ?? []}
          locale={{ emptyText: '老师暂未发布实训任务' }}
          renderItem={(task: TrainingTaskSummary) => (
            <List.Item
              actions={[
                <Button
                  key="start"
                  type="primary"
                  disabled={!studentId}
                  onClick={() => studentId && navigate(`/student/tasks/${task.id}?student=${encodeURIComponent(studentId)}`)}
                >
                  {studentId ? '开始任务 →' : '先选择学习档案'}
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={<Text strong>{task.title}</Text>}
                description={
                  <Space size={8} wrap>
                    <Tag color={DIFFICULTY_COLORS[task.difficulty]}>{DIFFICULTY_LABELS[task.difficulty]}</Tag>
                    <Text type="secondary">{task.est_minutes ? `预计 ${task.est_minutes} 分钟` : '时长待定'}</Text>
                    <Text type="secondary">训练 {task.skill_count} 项技能</Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>
      </>}

      {isDiagnosisPage && <section id="student-diagnostic-step" className="student-step-section student-step-section--diagnostic">
        <div className="student-diagnostic-content">
          <div id="student-learning-results" />

      {studentId && (profileQuery.isLoading || gapQuery.isLoading) && (
        <Skeleton active paragraph={{ rows: 8 }} />
      )}

      {studentId && profileQuery.isError && (
        <Alert
          type="info"
          showIcon
          title="尚无能力画像"
          description="该学生还没有完成诊断测评。点击上方「开始能力诊断」即可生成能力画像。"
          action={
            isDiagnosisPage ? (
              <Button type="primary" loading={startDiagnostic.isPending} onClick={() => startDiagnostic.mutate()}>
                开始能力诊断 →
              </Button>
            ) : undefined
          }
        />
      )}

      {studentId && diagnosticHint && (
        <Alert
          type="warning"
          showIcon
          title="诊断尚未准备好"
          description={diagnosticHint}
        />
      )}

      {studentId && gapQuery.data && hasDiagnosticResult && (
        <>
          <Row gutter={16} className="student-diagnostic-stat-row">
            <Col xs={24} md={8}>
              <Card size="small" className="student-diagnostic-stat student-diagnostic-stat--measured">
                <Statistic
                      title="已测评技能"
                      value={gaps.filter((g) => !g.untested).length}
                      suffix={
                        <Space size={6} className="student-diagnostic-stat__suffix">
                          <span>/ {gaps.length}</span>
                          {gaps.some((g) => g.untested) && (
                            <Tooltip title={gapQuery.data.notes.join('；')}>
                              <Tag color="gold">{gaps.filter((g) => g.untested).length} 项未考查</Tag>
                            </Tooltip>
                          )}
                        </Space>
                      }
                />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size="small" className="student-diagnostic-stat student-diagnostic-stat--achieved">
                <Statistic
                  title="已达标"
                  value={gaps.filter((g) => !g.untested && g.gap <= 0).length}
                  styles={{ content: { color: '#52c41a' } }}
                />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size="small" className="student-diagnostic-stat student-diagnostic-stat--evidence">
                <Statistic
                  title="证据充分的维度"
                  value={gaps.filter((g) => g.reliable).length}
                  suffix={`/ ${gaps.length}`}
                  styles={{
                    content: { color: gaps.some((g) => g.reliable) ? undefined : '#faad14' },
                  }}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={16} className="student-diagnostic-chart-row">
            <Col xs={24} lg={10}>
              <Card
                title="能力雷达图"
                size="small"
                className="student-diagnostic-chart student-diagnostic-chart--radar"
                extra={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    ⚠ 表示证据不足
                  </Text>
                }
              >
                <SkillRadar height={Math.max(420, (profile?.entries.length ?? 0) * 34 + 90)} gaps={gaps} />
              </Card>
            </Col>
            <Col xs={24} lg={14}>
              <Card
                title="能力区间"
                size="small"
                className="student-diagnostic-chart student-diagnostic-chart--interval"
                extra={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    色带越宽 = 越不确定
                  </Text>
                }
              >
                {profile && profile.entries.length > 0 ? (
                  <SkillIntervalChart entries={profile.entries} targets={targets} />
                ) : (
                  <Empty description="尚无测评数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Col>
          </Row>

          <Card title="查看能力差距" size="small" className="student-diagnostic-gap-table">
            <Table
              rowKey="skill_code"
              size="small"
              dataSource={gaps}
              columns={gapColumns}
              pagination={false}
            />
          </Card>

          <div className="student-diagnostic-next-action">
            <Button type="primary" size="large" onClick={() => navigate(`/student/path?student=${encodeURIComponent(studentId ?? '')}`)}>
              生成个性化学习 →
            </Button>
          </div>
        </>
      )}
        </div>
      </section>
      }

      <Modal
        title="新建学生"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => create.mutate()}
        confirmLoading={create.isPending}
        okButtonProps={{ disabled: !newName.trim() }}
        okText="创建"
        cancelText="取消"
      >
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            请填写<Text strong>化名</Text>（如「学生A」），
            不要填写真实姓名或学号 —— 系统不存储个人身份信息。
          </Paragraph>
          <Input
            placeholder="例如：学生A"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onPressEnter={() => newName.trim() && create.mutate()}
          />
        </Space>
      </Modal>
    </Space>
  )
}
