import { Alert, App, Button, Card, Progress, Select, Space, Table, Tag, Typography } from 'antd'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageHero } from '@/components/PageHero'
import { fetchCurriculumPlan, fetchCurriculumPlans, fetchGraph, fetchGraphs, fetchTasks, generateTask, toErrorMessage } from '@/services/api'
import type { GraphNode } from '@/types/graph'
import {
  DIFFICULTY_COLORS,
  DIFFICULTY_LABELS,
  TASK_STATUS_COLORS,
  TASK_STATUS_LABELS,
  type TrainingTaskSummary,
} from '@/types/training'

const { Text } = Typography

function flatten(nodes: GraphNode[]): GraphNode[] {
  return nodes.flatMap((node) => [node, ...flatten(node.children)])
}

/** STEP 03：查看、发布和管理从已审核图谱生成的实训任务。 */
export function TrainingTaskLibrary() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { message } = App.useApp()
  const requestedGraphId = searchParams.get('graph_id')
  const requestedNodeId = searchParams.get('node_id')
  const [selectedUnitId, setSelectedUnitId] = useState<string | undefined>(() => requestedNodeId ?? undefined)
  const [selectedPlanId, setSelectedPlanId] = useState<string | undefined>(() => searchParams.get('plan_id') ?? undefined)
  const [selectedCourseId, setSelectedCourseId] = useState<string | undefined>(() => searchParams.get('course_id') ?? undefined)
  const [generationProgress, setGenerationProgress] = useState(0)
  const tasksQuery = useQuery({ queryKey: ['tasks'], queryFn: () => fetchTasks() })
  const graphsQuery = useQuery({ queryKey: ['graphs'], queryFn: () => fetchGraphs() })
  const approvedGraph = graphsQuery.data?.items.find((graph) => graph.id === requestedGraphId && graph.status === 'approved')
    ?? graphsQuery.data?.items.find((graph) => graph.status === 'approved')
  const graphQuery = useQuery({
    queryKey: ['task-generator-graph', approvedGraph?.id],
    queryFn: () => fetchGraph(approvedGraph!.id),
    enabled: Boolean(approvedGraph),
  })
  const units = useMemo(
    () => (graphQuery.data ? flatten(graphQuery.data.tree).filter((node) => node.node_type === 'competency_unit') : []),
    [graphQuery.data],
  )
  const plansQuery = useQuery({ queryKey: ['curriculum-plans'], queryFn: fetchCurriculumPlans })
  const planQuery = useQuery({
    queryKey: ['task-generator-plan', selectedPlanId],
    queryFn: () => fetchCurriculumPlan(selectedPlanId!),
    enabled: Boolean(selectedPlanId),
  })
  const createTask = useMutation({
    mutationFn: (nodeId: string) => generateTask(nodeId, 'beginner', undefined, {
      planId: selectedPlanId,
      courseId: selectedCourseId,
    }),
    onSuccess: (task) => {
      message.success('实训任务已生成')
      setSelectedUnitId(undefined)
      navigate(`/teacher/tasks/${task.id}`)
    },
    onError: (error) => {
      setGenerationProgress(0)
      message.error(toErrorMessage(error))
    },
  })

  useEffect(() => {
    if (!createTask.isPending) return
    const timer = window.setInterval(() => {
      setGenerationProgress((current) => Math.min(current + 6, 90))
    }, 900)
    return () => window.clearInterval(timer)
  }, [createTask.isPending])

  const selectPlan = (planId: string | undefined) => {
    setSelectedPlanId(planId)
    setSelectedCourseId(undefined)
  }

  const columns = [
    {
      title: '实训任务',
      dataIndex: 'title',
      render: (title: string, row: TrainingTaskSummary) => <a onClick={() => navigate(`/teacher/tasks/${row.id}`)}>{title}</a>,
    },
    { title: '难度', dataIndex: 'difficulty', width: 100, render: (value: TrainingTaskSummary['difficulty']) => <Tag color={DIFFICULTY_COLORS[value]}>{DIFFICULTY_LABELS[value]}</Tag> },
    { title: '状态', dataIndex: 'status', width: 112, render: (value: TrainingTaskSummary['status']) => <Tag color={TASK_STATUS_COLORS[value]}>{TASK_STATUS_LABELS[value]}</Tag> },
    { title: '训练技能', dataIndex: 'skill_count', width: 110 },
    { title: '关联课程', width: 110, render: (_: unknown, row: TrainingTaskSummary) => row.course_id ? <Tag color="cyan">已关联课程</Tag> : row.plan_id ? <Tag color="blue">关联方案</Tag> : '—' },
    { title: '预计用时', dataIndex: 'est_minutes', width: 110, render: (value: number | null) => value ? `${value} 分钟` : '—' },
  ]

  return (
    <Space className="task-library" orientation="vertical" size={24} style={{ width: '100%' }}>
      <PageHero
        eyebrow="STEP 03 · 实训任务"
        title="生成、发布与管理实训任务"
        description="从审核通过的图谱能力单元生成学习型任务，核对任务内容后发布给学生完成。"
        actions={<Button className="task-library__back" onClick={() => navigate(-1)}>← 返回上一步</Button>}
      />

      <Card id="task-generator" className="task-generator-card" title="从能力图谱生成实训任务">
        {approvedGraph ? (
          <div className="task-generator-card__content">
            <div className="task-generator-card__intro">
              <strong>选择一个能力单元</strong>
              <Text type="secondary">系统会根据已审核图谱生成任务草案，生成后可继续编辑、设置要求并发布给学生。</Text>
            </div>
            <Select
              showSearch
              loading={graphQuery.isLoading}
              placeholder="请选择能力单元"
              value={selectedUnitId}
              onChange={setSelectedUnitId}
              options={units.map((unit) => ({ value: unit.id, label: unit.name }))}
              optionFilterProp="label"
              className="task-generator-card__select"
              notFoundContent={graphQuery.isLoading ? '正在加载能力单元…' : '没有可用于生成任务的能力单元'}
            />
            <div className="task-generator-card__curriculum">
              <strong>关联培养方案（可选）</strong>
              <Text type="secondary">选择课程后，任务会同时参考课程目标、教学内容和课程—技能映射；不选择时仍按原有图谱流程生成。</Text>
              <Space wrap style={{ width: '100%' }}>
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  loading={plansQuery.isLoading}
                  placeholder="选择已导入培养方案（可选）"
                  value={selectedPlanId}
                  onChange={selectPlan}
                  options={(plansQuery.data ?? []).map((plan) => ({ value: plan.id, label: plan.name }))}
                  className="task-generator-card__select"
                />
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  loading={planQuery.isLoading}
                  disabled={!selectedPlanId}
                  placeholder={selectedPlanId ? '选择关联课程（可选）' : '请先选择培养方案'}
                  value={selectedCourseId}
                  onChange={setSelectedCourseId}
                  options={(planQuery.data?.courses ?? []).map((course) => ({
                    value: course.id,
                    label: `${course.name}${course.total_hours ? ` · ${course.total_hours} 学时` : ''}`,
                  }))}
                  className="task-generator-card__select"
                />
              </Space>
              {selectedPlanId && !selectedCourseId && <Text type="secondary">将关联整个培养方案；如需指定课程，请继续选择课程。</Text>}
            </div>
            <Button
              type="primary"
              className="task-generator-card__button"
              loading={createTask.isPending}
              disabled={!selectedUnitId}
              onClick={() => {
                if (!selectedUnitId) return
                setGenerationProgress(12)
                createTask.mutate(selectedUnitId)
              }}
            >
              {createTask.isPending ? '正在生成任务…' : '生成实训任务 →'}
            </Button>
            {createTask.isPending && (
              <div className="task-generator-card__progress">
                <Progress percent={generationProgress} status="active" showInfo />
                <Text type="secondary">正在整理任务目标、步骤和评价要求，请稍候。</Text>
              </div>
            )}
          </div>
        ) : (
          <Alert type="info" showIcon message="请先完成 Step 2 图谱审核" description="审核通过一份能力图谱后，才能从其中的能力单元生成实训任务。" />
        )}
      </Card>

      <Card
        className="module-library-card"
        title="实训任务库"
        extra={
          <Space size={14}>
            <Text type="secondary">点击任务查看详情或发布状态</Text>
          </Space>
        }
      >
        {!approvedGraph && <Alert type="info" showIcon style={{ marginBottom: 16 }} message="请先完成 STEP 02 图谱审核" description="审核通过一份能力图谱后，打开图谱中的能力单元即可生成实训任务。" />}
        <Table
          rowKey="id"
          size="middle"
          loading={tasksQuery.isLoading}
          dataSource={tasksQuery.data?.items ?? []}
          columns={columns}
          pagination={false}
          locale={{ emptyText: approvedGraph ? '暂无实训任务。点击右上角“从图谱生成任务”开始。' : '暂无实训任务。请先审核通过能力图谱。' }}
        />
      </Card>

    </Space>
  )
}
