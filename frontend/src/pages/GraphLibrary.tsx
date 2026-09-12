import { Alert, App, Button, Card, Space, Table, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'

import { fetchGraphs, fetchSkills, generateGraph, toErrorMessage } from '@/services/api'
import type { GraphSummary } from '@/types/graph'
import { GRAPH_STATUS_COLORS, GRAPH_STATUS_LABELS } from '@/types/graph'

const { Text, Paragraph } = Typography
const TARGET_JOB = 'ai_data_annotator'

/** STEP 02：能力图谱的生成、版本查看与审核入口。 */
export function GraphLibrary() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const handoff = location.state as { focus?: string; selectedSkillCodes?: string[]; selectedSkillNames?: string[]; teachingGoal?: string } | null
  const queryClient = useQueryClient()
  const graphsQuery = useQuery({ queryKey: ['graphs'], queryFn: () => fetchGraphs() })
  const skillsQuery = useQuery({
    queryKey: ['skills', 'count'],
    queryFn: () => fetchSkills({ limit: 1 }),
  })
  const skillCount = skillsQuery.data?.total ?? 0

  const returnToPrevious = () => {
    if ((window.history.state?.idx ?? 0) > 0) {
      navigate(-1)
      return
    }
    navigate('/teacher')
  }

  const generate = useMutation({
    mutationFn: () => generateGraph(TARGET_JOB, handoff?.focus, handoff?.selectedSkillCodes),
    onSuccess: (graph) => {
      message.success(`已生成图谱草案：${graph.node_count} 个节点`)
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
        <a onClick={() => navigate(`/teacher/graphs/${row.id}`)}>{title ?? row.id}</a>
      ),
    },
    { title: '版本', dataIndex: 'version', width: 88, render: (version: number) => `v${version}` },
    {
      title: '状态',
      dataIndex: 'status',
      width: 108,
      render: (status: GraphSummary['status']) => (
        <Tag color={GRAPH_STATUS_COLORS[status]}>{GRAPH_STATUS_LABELS[status]}</Tag>
      ),
    },
    { title: '节点数', dataIndex: 'node_count', width: 96 },
    { title: '技能点', dataIndex: 'skill_point_count', width: 96 },
    { title: '审核人', dataIndex: 'approved_by', width: 132, render: (value: string | null) => value ?? <Text type="secondary">—</Text> },
  ]

  return (
    <Space className="graph-library" orientation="vertical" size={18} style={{ width: '100%' }}>
      <section className="graph-library__hero">
        <Button className="graph-library__back" onClick={returnToPrevious}>← 返回上一步</Button>
        <Tag className="graph-library__eyebrow">STEP 02 · 能力图谱</Tag>
        <div className="graph-library__title-wrap"><h1 className="graph-library__title">生成并审核岗位能力图谱</h1></div>
        <Paragraph>将岗位需求转化为能力草案；审核技能、知识点和依据后，才能用于生成实训任务。</Paragraph>
      </section>

      <Card className="graph-create-panel">
        <div className="graph-create-panel__content">
          <div>
            <Text strong>开始生成能力图谱</Text>
            <Text type="secondary">系统将根据岗位需求、已选能力和教学目标生成一份待审核草案。</Text>
          </div>
          <Button className="graph-library__generate" type="primary" loading={generate.isPending} disabled={skillCount === 0} onClick={() => generate.mutate()}>生成新图谱 →</Button>
        </div>
      </Card>

      {handoff?.focus ? (
        <Alert
          type="success"
          showIcon
          message="已带入教师的图谱设计决策"
          description={`本次图谱仅纳入：${handoff.selectedSkillNames?.join('、')}。${handoff.teachingGoal ? ` 教学目标：${handoff.teachingGoal}` : ''}`}
        />
      ) : null}

      <Card className="module-library-card" title="能力图谱库" extra={<Text type="secondary">选择一份图谱进入审核</Text>}>
        {skillCount === 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="技能规范表为空"
            description={<span>请先运行 <Text code>python scripts/seed_skills.py</Text> 导入技能规范表后再生成图谱。</span>}
          />
        )}
        {generate.isPending && <Alert type="info" showIcon style={{ marginBottom: 16 }} message="正在生成能力图谱" description="请勿关闭页面，生成完成后会自动进入审核页。" />}
        <Table
          rowKey="id"
          size="middle"
          loading={graphsQuery.isLoading}
          dataSource={graphsQuery.data?.items ?? []}
          columns={columns}
          pagination={false}
          locale={{ emptyText: '暂无能力图谱。点击右上角“生成新图谱”开始。' }}
        />
      </Card>

      <Card size="small" className="module-evidence-card" title="图谱依据与使用说明">
        <Space orientation="vertical" size={4}>
          <Text type="secondary">图谱依据：<Text strong>{skillCount} 条职业技能规范</Text>，均抽取自《人工智能训练师国家职业技能标准（2021年版）》，每条均可溯源至具体页码。</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>图谱由 AI 生成草案、教师审核确认。审核通过后节点编码冻结，供课程映射、实训任务与学生能力测评引用。</Text>
        </Space>
      </Card>
    </Space>
  )
}
