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
import { Link, useParams } from 'react-router-dom'

import { CompetencyTree, TreeLegend } from '@/charts/CompetencyTree'
import { NodeDetailPanel } from '@/components/NodeDetailPanel'
import { approveGraph, fetchGraph, toErrorMessage } from '@/services/api'
import type { GraphNode } from '@/types/graph'
import { GRAPH_STATUS_COLORS, GRAPH_STATUS_LABELS } from '@/types/graph'

const { Title, Text, Paragraph } = Typography

function flatten(nodes: GraphNode[]): GraphNode[] {
  return nodes.flatMap((node) => [node, ...flatten(node.children)])
}

export function GraphReview() {
  const { graphId = '' } = useParams()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [approveOpen, setApproveOpen] = useState(false)
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
        <Col>
          {isDraft ? (
            <Button type="primary" onClick={() => setApproveOpen(true)}>
              审核通过
            </Button>
          ) : (
            <Text type="secondary">
              {data.approved_by ? `已由 ${data.approved_by} 审核通过` : '已归档'}
            </Text>
          )}
        </Col>
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

      <Row gutter={16}>
        <Col xs={24} lg={15}>
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
        <Col xs={24} lg={9}>
          <Card title="节点详情与依据" style={{ minHeight: 400 }}>
            <NodeDetailPanel
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
    </Space>
  )
}
