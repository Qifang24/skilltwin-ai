import { Button, Card, Col, Row, Space, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { PageHero } from '@/components/PageHero'
import { fetchGraphs, fetchJobMarketDashboard, fetchSkills, fetchStudents, fetchTasks } from '@/services/api'

const { Title, Paragraph, Text } = Typography
const TARGET_JOB = 'ai_data_annotator'

/** 教师端首页只承担导航职责；图谱与实训内容分别在 STEP 02、03 模块管理。 */
export function TeacherWorkspace() {
  const navigate = useNavigate()
  const skillsQuery = useQuery({
    queryKey: ['skills', 'count'],
    queryFn: () => fetchSkills({ limit: 1 }),
  })
  const marketQuery = useQuery({
    queryKey: ['job-market', TARGET_JOB],
    queryFn: () => fetchJobMarketDashboard(TARGET_JOB),
  })
  const graphsQuery = useQuery({ queryKey: ['graphs'], queryFn: () => fetchGraphs() })
  const tasksQuery = useQuery({ queryKey: ['tasks'], queryFn: () => fetchTasks() })
  const studentsQuery = useQuery({ queryKey: ['students'], queryFn: fetchStudents })
  const skillCount = skillsQuery.data?.total ?? 0
  const approvedGraph = graphsQuery.data?.items.find((graph) => graph.status === 'approved')
  const draftGraph = graphsQuery.data?.items.find((graph) => graph.status === 'draft')
  const projectStats = [
    {
      label: '岗位需求样本',
      value: marketQuery.data?.data_quality.real_postings ?? 0,
      suffix: '条真实 JD',
      detail: marketQuery.data ? `已导入 ${marketQuery.data.data_quality.total_postings} 条岗位信息` : '正在读取岗位数据',
      className: 'project-progress__item--brown',
    },
    {
      label: '能力图谱',
      value: approvedGraph ? '已审核' : draftGraph ? '待审核' : '未生成',
      suffix: '',
      detail: approvedGraph ? `${approvedGraph.node_count} 个节点可用于实训` : draftGraph ? '请进入 STEP 02 进行确认' : '请进入 STEP 02 生成图谱',
      className: 'project-progress__item--pink',
    },
    {
      label: '实训任务',
      value: tasksQuery.data?.total ?? 0,
      suffix: '项',
      detail: (tasksQuery.data?.total ?? 0) ? '可进入 STEP 03 查看与发布' : '确认图谱后即可生成',
      className: 'project-progress__item--purple',
    },
    {
      label: '学生档案',
      value: studentsQuery.data?.length ?? 0,
      suffix: '名',
      detail: (studentsQuery.data?.length ?? 0) ? '可在学生端开展诊断' : '创建学生后即可开展诊断',
      className: 'project-progress__item--blue',
    },
  ]

  const workflowSteps = [
    {
      step: '01',
      title: '分析岗位需求',
      description: '基于真实招聘信息，梳理岗位所需技能和典型工作内容。',
      label: '开始岗位分析',
      onClick: () => navigate('/teacher/market'),
    },
    {
      step: '02',
      title: '构建岗位能力图谱',
      description: '核对 AI 生成的能力、技能点和来源，确认后作为实训设计依据。',
      label: '进入图谱审核',
      onClick: () => navigate('/teacher/graphs'),
    },
    {
      step: '03',
      title: '生成并发布实训任务',
      description: '依据已确认图谱生成学习型任务，检查后发布给学生完成。',
      label: '生成实训任务',
      onClick: () => navigate('/teacher/tasks'),
    },
  ]

  return (
    <Space className="teacher-workspace" orientation="vertical" size={14} style={{ width: '100%' }}>
      <PageHero
        eyebrow="教师工作台 · 实训任务设计"
        title="从岗位需求到实训任务"
        description="分析真实岗位需求，构建岗位能力图谱，生成并发布学生实训任务。"
        meta={<Space wrap><Tag color="blue">目标岗位 · AI 数据标注工程师</Tag><Tag color="green">{skillCount} 条技能规范已就绪</Tag></Space>}
        actions={<Button type="primary" onClick={() => navigate('/teacher/market')}>从岗位需求开始</Button>}
      />

      <Card className="workflow-card" title="三步完成实训任务设计" extra={<Text type="secondary">从真实岗位需求到可发布的学生实训任务</Text>}>
        <Row gutter={[12, 12]}>
          {workflowSteps.map(({ step, title, description, label, onClick }) => (
            <Col xs={24} md={8} key={step}>
              <Card size="small" className={`workflow-step workflow-step--${step}`}>
                <div className="workflow-step__top"><span className="workflow-step__number">STEP {step}</span></div>
                <Title level={5}>{title}</Title>
                <Paragraph type="secondary">{description}</Paragraph>
                <Button className="workflow-step__action" type="default" onClick={onClick}>{label} →</Button>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card className="project-progress" title="当前教学项目进度" extra={<Text type="secondary">四项状态实时同步</Text>}>
        <Row gutter={[12, 12]}>
          {projectStats.map((stat) => (
            <Col xs={12} lg={6} key={stat.label}>
              <div className={`project-progress__item ${stat.className}`}>
                <Text className="project-progress__label">{stat.label}</Text>
                <div className="project-progress__value"><strong>{stat.value}</strong><span>{stat.suffix}</span></div>
                <Text className="project-progress__detail">{stat.detail}</Text>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

    </Space>
  )
}
