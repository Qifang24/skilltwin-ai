/**
 * 图谱审核页 —— 教师查看、修改、通过。
 *
 * 布局刻意做成左树右详情：教师的工作方式是「看到结构 → 点开某项 → 核对依据 →
 * 改或不改」，两栏并置才能不来回跳转。
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
  Modal,
  Result,
  Row,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { CompetencyTree, TreeLegend } from '@/charts/CompetencyTree'
import { NodeDetailPanel } from '@/components/NodeDetailPanel'
import { approveGraph, deleteGraph, fetchGraph, toErrorMessage } from '@/services/api'
import type { GraphNode } from '@/types/graph'
import { GRAPH_STATUS_COLORS, GRAPH_STATUS_LABELS } from '@/types/graph'

const { Title, Text, Paragraph } = Typography

function flatten(nodes: GraphNode[]): GraphNode[] {
  return nodes.flatMap((node) => [node, ...flatten(node.children)])
}

export function GraphReview() {
  const { graphId = '' } = useParams()
  const navigate = useNavigate()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [approveOpen, setApproveOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [reviewer, setReviewer] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['graph', graphId],
    queryFn: () => fetchGraph(graphId),
    enabled: Boolean(graphId),
  })

  const flatNodes = useMemo(() => (data ? flatten(data.tree) : []), [data])
  const selected = flatNodes.find((n) => n.id === selectedId) ?? null

  const approve = useMutation({
    mutationFn: () => approveGraph(graphId, reviewer.trim()),
    onSuccess: () => {
      message.success('图谱已通过审核，节点编码已冻结')
      setApproveOpen(false)
      queryClient.invalidateQueries({ queryKey: ['graph', graphId] })
      queryClient.invalidateQueries({ queryKey: ['graphs'] })
    },
    onError: (err) => message.error(toErrorMessage(err)),
  })

  const remove = useMutation({
    mutationFn: () => deleteGraph(graphId),
    onSuccess: () => {
      message.success('图谱草稿已删除')
      queryClient.invalidateQueries({ queryKey: ['graphs'] })
      navigate('/teacher/graphs')
    },
    onError: (err) => message.error(toErrorMessage(err)),
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['graph', graphId] })
  }

  if (isLoading) return <Skeleton active paragraph={{ rows: 10 }} />

  if (error || !data) {
    return (
      <Result
        status="error"
        title="无法加载图谱"
        subTitle={toErrorMessage(error)}
        extra={
          <Link to="/teacher">
            <Button type="primary">返回工作台</Button>
          </Link>
        }
      />
    )
  }

  const isDraft = data.status === 'draft'
  const editedCount = flatNodes.filter((n) => n.edited_by_human).length
  const noEvidenceCount = flatNodes.filter(
    (n) => n.evidence.length === 0 && n.node_type !== 'job' && !n.skill_code,
  ).length
  const skillNodes = flatNodes.filter((node) => Boolean(node.skill_code))
  const standardNodes = flatNodes.filter(
    (node) => node.node_type !== 'job' && !node.skill_code,
  )
  const nodesWithoutJobEvidence = skillNodes.filter(
    (node) => !node.evidence.some((evidence) => evidence.type === 'job_posting'),
  )
  const nodesWithoutStandardEvidence = standardNodes.filter(
    (node) => node.evidence.length === 0,
  )
  const nodesWithoutDescription = flatNodes.filter(
    (node) => node.node_type !== 'job' && !node.description?.trim(),
  )
  const graphSkillCodes = new Set(
    skillNodes.flatMap((node) => (node.skill_code ? [node.skill_code] : [])),
  )
  const selectedSkillCodes = data.selected_skill_codes ?? []
  const missingSelectedCodes = selectedSkillCodes.filter(
    (code) => !graphSkillCodes.has(code),
  )
  const selectedIncludedCount = selectedSkillCodes.length - missingSelectedCodes.length

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Breadcrumb
        items={[
          { title: <Link to="/teacher">教师工作台</Link> },
          { title: data.title ?? graphId },
        ]}
      />

      <Row justify="space-between" align="middle" gutter={[16, 16]}>
        <Col>
          <Space align="center" size={12}>
            <Title level={3} style={{ margin: 0 }}>
              {data.title ?? graphId}
            </Title>
            <Tag color={GRAPH_STATUS_COLORS[data.status]}>
              {GRAPH_STATUS_LABELS[data.status]}
            </Tag>
            <Tag color="blue">AI 生成</Tag>
          </Space>
        </Col>
        {!isDraft && (
          <Col>
            <Text type="secondary">
              {data.approved_by ? `已由 ${data.approved_by} 审核通过` : '已归档'}
            </Text>
          </Col>
        )}
      </Row>

      {data.summary && <Paragraph type="secondary">{data.summary}</Paragraph>}

      <Descriptions size="small" column={4} bordered>
        <Descriptions.Item label="节点总数">{data.node_count}</Descriptions.Item>
        <Descriptions.Item label="技能点">{data.skill_point_count}</Descriptions.Item>
        <Descriptions.Item label="经教师修订">{editedCount}</Descriptions.Item>
        <Descriptions.Item label="缺依据节点">
          {noEvidenceCount > 0 ? (
            <Text type="warning">{noEvidenceCount}</Text>
          ) : (
            0
          )}
        </Descriptions.Item>
      </Descriptions>



      {data.warnings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="生成过程中的提示"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {data.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          }
        />
      )}

      {!isDraft && (
        <Alert
          type="info"
          showIcon
          message="该图谱已审核通过，节点编码已冻结"
          description="已审核的图谱不可修改——下游的课程映射、实训任务与学生能力向量都引用这些编码。如需调整，请回到工作台生成新版本。"
        />
      )}

      {data.status === 'approved' && (
        <Card className="graph-next-step-card" size="small">
          <div className="graph-next-step-card__content">
            <div>
              <strong>下一步：生成实训任务</strong>
              <Text type="secondary">
                从已审核的能力单元生成任务，再设置发布对象与要求。
              </Text>
            </div>
            <Link to="/teacher/tasks">
              <Button className="graph-next-step-card__button">
                进入 Step 3 实训任务设计 →
              </Button>
            </Link>
          </div>
        </Card>
      )}

      <Row gutter={16}>
        <Col xs={24} lg={24}>
          <Card
            title="能力图谱"
            styles={{ body: { padding: 12 } }}
            extra={<TreeLegend />}
          >
            <CompetencyTree
              tree={data.tree}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </Card>
        </Col>
        <Col xs={24} lg={24}>
          <Card className="graph-node-detail-card" title="节点详情与依据" style={{ minHeight: 400 }}>
            <NodeDetailPanel
              key={selected?.id ?? 'no-node-selected'}
              graphId={graphId}
              node={selected}
              editable={isDraft}
              approved={data.status === 'approved'}
              onChanged={() => {
                setSelectedId(null)
                refresh()
              }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card
            size="small"
            className="graph-readiness-card graph-readiness-card--coverage"
            title="重点能力覆盖概览"
          >
            {selectedSkillCodes.length > 0 ? (
              <>
                <div className="graph-readiness__headline">
                  <strong>{selectedIncludedCount}</strong>
                  <span>/{selectedSkillCodes.length} 项第一步选定技能已纳入图谱</span>
                </div>
                {missingSelectedCodes.length > 0 ? (
                  <div className="graph-readiness__warning">
                    尚未生成：{missingSelectedCodes.join('、')}
                  </div>
                ) : (
                  <Text type="success">已完整覆盖本次选定的重点能力。</Text>
                )}
              </>
            ) : (
              <Text type="secondary">
                未带入第一步的重点能力清单；本图谱按全部有效技能生成。
              </Text>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={14}>
          <Card
            size="small"
            className="graph-readiness-card graph-readiness-card--checklist"
            title="审核前检查清单"
          >
            <div className="graph-readiness__item">
              <Tag color={missingSelectedCodes.length ? 'warning' : 'success'}>
                {missingSelectedCodes.length ? '待补充' : '已完成'}
              </Tag>
              <strong>重点能力覆盖</strong>
              <span>{selectedSkillCodes.length ? `已纳入 ${selectedIncludedCount}/${selectedSkillCodes.length} 项` : '未设置重点能力范围'}</span>
            </div>
            <div className="graph-readiness__item">
              <Tag color={nodesWithoutJobEvidence.length ? 'warning' : 'success'}>
                {nodesWithoutJobEvidence.length ? '待补充' : '已完成'}
              </Tag>
              <strong>岗位原文依据</strong>
              <span>{skillNodes.length - nodesWithoutJobEvidence.length}/{skillNodes.length} 个技能点已关联 JD 原文</span>
            </div>
            <div className="graph-readiness__item">
              <Tag color={nodesWithoutStandardEvidence.length ? 'warning' : 'success'}>
                {nodesWithoutStandardEvidence.length ? '待补充' : '已完成'}
              </Tag>
              <strong>职业标准依据</strong>
              <span>{standardNodes.length - nodesWithoutStandardEvidence.length}/{standardNodes.length} 个能力节点有标准依据</span>
            </div>
            <div className="graph-readiness__item">
              <Tag color={nodesWithoutDescription.length ? 'warning' : 'success'}>
                {nodesWithoutDescription.length ? '待补充' : '已完成'}
              </Tag>
              <strong>节点说明完整</strong>
              <span>{nodesWithoutDescription.length ? `${nodesWithoutDescription.length} 个节点缺少说明` : '所有非岗位节点均已填写说明'}</span>
            </div>
          </Card>
        </Col>
      </Row>

      {isDraft && (
        <div className="graph-review__decision-area">
          <Space className="graph-review__actions" size={14} wrap>
            <Button className="graph-review__reject" onClick={() => setRejectOpen(true)}>
              审核不通过
            </Button>
            <Button className="graph-review__delete" danger onClick={() => setDeleteOpen(true)}>
              删除草稿
            </Button>
            <Button className="graph-review__approve" onClick={() => setApproveOpen(true)}>
              审核通过
            </Button>
          </Space>
        </div>
      )}

      <Modal
        title="审核通过"
        open={approveOpen}
        onCancel={() => setApproveOpen(false)}
        onOk={() => approve.mutate()}
        okText="确认通过"
        cancelText="取消"
        confirmLoading={approve.isPending}
        okButtonProps={{ disabled: !reviewer.trim() }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            通过后节点编码将被冻结，可供课程映射、实训任务与学生能力测评引用。
            同一岗位此前已通过的图谱会自动归档。
          </Paragraph>
          <Input
            placeholder="请输入审核人姓名"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            onPressEnter={() => reviewer.trim() && approve.mutate()}
          />
        </Space>
      </Modal>

      <Modal
        title="审核不通过"
        open={rejectOpen}
        onCancel={() => setRejectOpen(false)}
        onOk={() => {
          setRejectOpen(false)
          message.info('图谱未通过审核，已保留在草稿库中，可继续修改后再次提交。')
          navigate('/teacher/graphs')
        }}
        okText="保留为草稿"
        cancelText="取消"
      >
        <Paragraph style={{ marginBottom: 0 }}>
          此图谱不会用于实训任务或学生测评，并会保留在能力图谱库中供后续修改。
        </Paragraph>
      </Modal>

      <Modal
        title="删除图谱草稿"
        open={deleteOpen}
        onCancel={() => setDeleteOpen(false)}
        onOk={() => remove.mutate()}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={remove.isPending}
      >
        <Paragraph style={{ marginBottom: 0 }}>
          将永久删除这份草稿及全部节点，此操作无法恢复。
        </Paragraph>
      </Modal>
    </Space>
  )
}
