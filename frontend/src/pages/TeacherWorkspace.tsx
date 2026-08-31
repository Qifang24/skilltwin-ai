/**
 * 教师工作台：图谱列表 + 生成入口。
 */

import { App, Alert, Button, Card, Col, Row, Space, Table, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import {
  fetchGraphs,
  fetchSkills,
  fetchTasks,
  generateGraph,
  toErrorMessage,
} from '@/services/api'
import type { GraphSummary } from '@/types/graph'
import { GRAPH_STATUS_COLORS, GRAPH_STATUS_LABELS } from '@/types/graph'
import type { TrainingTaskSummary } from '@/types/training'
import { PageHero } from '@/components/PageHero'
import {
  DIFFICULTY_COLORS,
  DIFFICULTY_LABELS,
  TASK_STATUS_COLORS,
  TASK_STATUS_LABELS,
} from '@/types/training'

const { Title, Paragraph, Text } = Typography

const TARGET_JOB = 'ai_data_annotator'

export function TeacherWorkspace() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const graphsQuery = useQuery({
    queryKey: ['graphs'],
    queryFn: () => fetchGraphs(),
  })
  const tasksQuery = useQuery({
    queryKey: ['tasks'],
    queryFn: () => fetchTasks(),
  })
  const skillsQuery = useQuery({
    queryKey: ['skills', 'count'],
    queryFn: () => fetchSkills({ limit: 1 }),
  })

  const generate = useMutation({
    mutationFn: () => generateGraph(TARGET_JOB),
    onSuccess: (graph) => {
      message.success(`已生成草案：${graph.node_count} 个节点`)
      queryClient.invalidateQueries({ queryKey: ['graphs'] })
      navigate(`/teacher/graphs/${graph.id}`)
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })

  const columns = [
    {
      title: '图谱',
      dataIndex: 'title',
      render: (title: string | null, row: GraphSummary) => (
        <a onClick={() => navigate(`/teacher/graphs/${row.id}`)}>
          {title ?? row.id}
        </a>
      ),
    },
    {
      title: '版本',
      dataIndex: 'version',
      width: 80,
      render: (v: number) => `v${v}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: GraphSummary['status']) => (
        <Tag color={GRAPH_STATUS_COLORS[status]}>{GRAPH_STATUS_LABELS[status]}</Tag>
      ),
    },
    { title: '节点数', dataIndex: 'node_count', width: 90 },
    { title: '技能点', dataIndex: 'skill_point_count', width: 90 },
    {
      title: '审核人',
      dataIndex: 'approved_by',
      width: 120,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
  ]

  const skillCount = skillsQuery.data?.total ?? 0

  return (
    <Space orientation="vertical" size={24} style={{ width: '100%' }}>
      <PageHero
        eyebrow="教师端 · 专业群建设"
        title="从产业需求，走到教学实训"
        description="以可回查的岗位证据为起点，形成能力图谱、课程 Gap、实训任务与培养方案优化的教学闭环。"
        meta={<Space wrap><Tag color="blue">目标岗位：AI 数据标注工程师</Tag><Tag color="green">技能规范表 {skillCount} 条</Tag></Space>}
        actions={<Button type="primary" onClick={() => navigate('/teacher/market')}>查看岗位需求</Button>}
      />

      <Card className="workflow-card" title="比赛演示主线" extra={<Text type="secondary">证据驱动 · 每一步可回查</Text>}>
        <Row gutter={[12, 12]}>
          {[
            ['01', '产业需求', '查看公开 JD 的技能频率、趋势与原文证据', '/teacher/market', '岗位看板'],
            ['02', '课程对标', '识别课程覆盖、未映射项与岗位能力 Gap', '/teacher/curriculum-gap', 'Gap 分析'],
            ['03', '教学优化', '按需求频率与覆盖比例给出调整优先级', '/teacher/curriculum-optimization', '优化建议'],
            ['04', '真实验证', '用匿名脚本记录教师与学生的实际使用反馈', '/teacher/user-testing', '测试报告'],
          ].map(([step, title, description, route, label]) => (
            <Col xs={24} sm={12} lg={6} key={step}>
              <Card size="small" className="workflow-step">
                <Tag color="blue">STEP {step}</Tag>
                <Title level={5}>{title}</Title>
                <Paragraph type="secondary">{description}</Paragraph>
                <Button type="link" onClick={() => navigate(route)}>{label} →</Button>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card
        title="岗位能力图谱"
        extra={
          <Button
            type="primary"
            loading={generate.isPending}
            disabled={skillCount === 0}
            onClick={() => generate.mutate()}
          >
            {generate.isPending ? '生成中（约 1 分钟）…' : '生成新图谱'}
          </Button>
        }
      >
        {skillCount === 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="技能规范表为空"
            description={
              <span>
                请先运行 <Text code>python scripts/seed_skills.py</Text> 载入技能表。
                技能编码是全系统的关联键，没有它图谱无法生成。
              </span>
            }
          />
        )}

        {generate.isPending && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="正在检索标准条文并生成图谱"
            description="包含知识库混合检索与模型生成两个阶段，请勿关闭页面。"
          />
        )}

        <Table
          rowKey="id"
          size="small"
          loading={graphsQuery.isLoading}
          dataSource={graphsQuery.data?.items ?? []}
          columns={columns}
          pagination={false}
          locale={{ emptyText: '暂无图谱，点击右上角生成' }}
        />
      </Card>

      <Card
        title="岗位需求趋势分析"
        extra={<Button onClick={() => navigate('/teacher/market')}>进入看板</Button>}
      >
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          从已导入的公开岗位 JD 中提取有原文证据的技能需求排名与月度趋势。样本量、DEMO 标识和数据质量警告均会同时展示。
        </Paragraph>
      </Card>

      <Card title="课程覆盖与岗位能力 Gap" extra={<Button onClick={() => navigate('/teacher/curriculum-gap')}>进入分析</Button>}>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>按课程原文证据核验已覆盖技能；未结构化的课程会明确提示，避免将资料缺失误作培养缺口。</Paragraph>
      </Card>
      <Card title="人才培养方案优化建议" extra={<Button onClick={() => navigate('/teacher/curriculum-optimization')}>查看建议</Button>}>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>仅在岗位样本可靠时，按“需求频率 × 未覆盖比例”生成可回溯的课程调整优先级。</Paragraph>
      </Card>

      <Card title="真实用户测试" extra={<Button onClick={() => navigate('/teacher/user-testing')}>记录与报告</Button>}>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>使用教师、学生的匿名测试脚本记录实际结果、达成度与易用性；仅已完成的真实记录会被汇总，样本不足时系统不会生成结论。</Paragraph>
      </Card>

      <Card title="实训任务">
        <Table
          rowKey="id"
          size="small"
          loading={tasksQuery.isLoading}
          dataSource={tasksQuery.data?.items ?? []}
          pagination={false}
          locale={{
            emptyText: '暂无任务。打开已审核的图谱，点击能力单元节点即可生成',
          }}
          columns={[
            {
              title: '任务',
              dataIndex: 'title',
              render: (title: string, row: TrainingTaskSummary) => (
                <a onClick={() => navigate(`/teacher/tasks/${row.id}`)}>{title}</a>
              ),
            },
            {
              title: '难度',
              dataIndex: 'difficulty',
              width: 90,
              render: (d: TrainingTaskSummary['difficulty']) => (
                <Tag color={DIFFICULTY_COLORS[d]}>{DIFFICULTY_LABELS[d]}</Tag>
              ),
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (s: TrainingTaskSummary['status']) => (
                <Tag color={TASK_STATUS_COLORS[s]}>{TASK_STATUS_LABELS[s]}</Tag>
              ),
            },
            { title: '训练技能', dataIndex: 'skill_count', width: 100 },
            {
              title: '用时',
              dataIndex: 'est_minutes',
              width: 90,
              render: (m: number | null) => (m ? `${m} 分钟` : '—'),
            },
          ]}
        />
      </Card>

      <Card size="small">
        <Space orientation="vertical" size={4}>
          <Text type="secondary">
            技能规范表现有 <Text strong>{skillCount}</Text> 条，
            均抽取自《人工智能训练师国家职业技能标准（2021年版）》，每条可溯源到具体页码。
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            图谱由 AI 生成草案、教师审核确认。审核通过后节点编码冻结，
            供课程映射、实训任务与学生能力测评引用。
          </Text>
        </Space>
      </Card>
    </Space>
  )
}
