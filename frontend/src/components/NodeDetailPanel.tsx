/**
 * 节点详情与编辑面板。
 *
 * 这是「可解释性」在界面上的落点：每个能力节点都要能回答
 * 「凭什么在图谱里」—— 展示来源、章节、页码与原文引文，供教师核验。
 */

import {
  App,
  Button,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Space,
  Tag,
  Typography,
} from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import { useEffect, useState } from 'react'

import { useNavigate } from 'react-router-dom'

import {
  deleteGraphNode,
  generateTask,
  linkGraphNodeJobEvidence,
  toErrorMessage,
  updateGraphNode,
} from '@/services/api'
import type { GraphNode } from '@/types/graph'
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from '@/types/graph'

const { Paragraph, Text } = Typography

interface NodeDetailPanelProps {
  graphId: string
  node: GraphNode | null
  editable: boolean
  /** 图谱是否已审核 —— 只有已审核的节点可派生实训任务 */
  approved: boolean
  onChanged: () => void
}

export function NodeDetailPanel({
  graphId,
  node,
  editable,
  approved,
  onChanged,
}: NodeDetailPanelProps) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [generating, setGenerating] = useState(false)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    setEditing(false)
    if (node) {
      form.setFieldsValue({
        name: node.name,
        description: node.description ?? '',
        teacher_note: node.teacher_note ?? '',
        mastery_level: node.mastery_level ?? undefined,
      })
    }
  }, [node, form])

  if (!node) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="点击左侧图谱中的节点查看详情与依据"
      />
    )
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      await updateGraphNode(graphId, node.id, {
        name: values.name,
        description: values.description || null,
        teacher_note: values.teacher_note || null,
        mastery_level: values.mastery_level ?? null,
      })
      message.success('已保存')
      setEditing(false)
      onChanged()
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(toErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleGenerateTask = async () => {
    if (!node) return
    setGenerating(true)
    try {
      const task = await generateTask(node.id)
      message.success('实训任务已生成')
      navigate(`/teacher/tasks/${task.id}`)
    } catch (error) {
      message.error(toErrorMessage(error))
    } finally {
      setGenerating(false)
    }
  }

  const handleDelete = async () => {
    try {
      const result = await deleteGraphNode(graphId, node.id)
      message.success(`已删除 ${result.removed} 个节点`)
      onChanged()
    } catch (error) {
      message.error(toErrorMessage(error))
    }
  }

  const removeJobEvidence = async (postingId: string) => {
    if (!node) return
    const remaining = node.evidence
      .filter((item) => item.type === 'job_posting' && item.posting_id && item.posting_id !== postingId)
      .map((item) => item.posting_id as string)
    try {
      await linkGraphNodeJobEvidence(graphId, node.id, remaining)
      message.success('已移除该岗位原文依据')
      onChanged()
    } catch (error) {
      message.error(toErrorMessage(error))
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space size={8} wrap>
        <Tag color={NODE_TYPE_COLORS[node.node_type]}>
          {NODE_TYPE_LABELS[node.node_type]}
        </Tag>
        {node.ai_generated ? (
          <Tag color="blue">AI 生成</Tag>
        ) : (
          <Tag color="purple">人工添加</Tag>
        )}
        {node.edited_by_human && <Tag color="gold">经教师修订</Tag>}
      </Space>

      {editing ? (
        <Form form={form} layout="vertical" size="small">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '名称不能为空' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="teacher_note" label="教师备注">
            <Input.TextArea rows={4} maxLength={2000} showCount placeholder="记录审核观察、教学提醒或后续调整想法" />
          </Form.Item>
          {node.skill_code && (
            <Form.Item
              name="mastery_level"
              label="掌握程度（1 了解 / 2 理解 / 3 掌握 / 4 熟练）"
            >
              <InputNumber min={1} max={4} style={{ width: '100%' }} />
            </Form.Item>
          )}
          <Space>
            <Button type="primary" size="small" loading={saving} onClick={handleSave}>
              保存
            </Button>
            <Button size="small" onClick={() => setEditing(false)}>
              取消
            </Button>
          </Space>
        </Form>
      ) : (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="名称">{node.name}</Descriptions.Item>
            {node.description && (
              <Descriptions.Item label="说明">{node.description}</Descriptions.Item>
            )}
            {node.teacher_note && (
              <Descriptions.Item label="教师备注">
                <div className="node-teacher-note">{node.teacher_note}</div>
              </Descriptions.Item>
            )}
            {node.skill_code && (
              <Descriptions.Item label="技能编码">
                <Text code>{node.skill_code}</Text>
              </Descriptions.Item>
            )}
            {node.mastery_label && (
              <Descriptions.Item label="掌握程度">
                <Tag>{`${node.mastery_level} · ${node.mastery_label}`}</Tag>
              </Descriptions.Item>
            )}
            <Descriptions.Item label="节点 ID">
              <Text code style={{ fontSize: 11 }}>
                {node.id}
              </Text>
            </Descriptions.Item>
          </Descriptions>

          {editable && (
            <div className="node-detail-actions"><Space size={12}>
              <Button size="small" onClick={() => setEditing(true)}>
                修改/备注
              </Button>
              <Popconfirm
                title="删除该节点"
                description="其下所有子节点会一并删除，此操作不可撤销。"
                okText="确认删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={handleDelete}
              >
                <Button size="small" danger>
                  删除
                </Button>
              </Popconfirm>
            </Space></div>
          )}
        </>
      )}

      {approved && node.node_type === 'competency_unit' && (
        <Button
          type="primary"
          block
          loading={generating}
          onClick={handleGenerateTask}
        >
          {generating ? '生成中（约 1 分钟）…' : '由此能力生成实训任务'}
        </Button>
      )}

      <div className="node-evidence-section">
        <Text strong>依据</Text>
        {node.evidence.length === 0 ? (
          <div className="node-evidence-section__missing">
            <Text strong>待补充依据</Text>
            <Paragraph style={{ margin: '4px 0 0' }}>该节点尚未关联职业标准或岗位原文，请核实来源后再通过审核。</Paragraph>
          </div>
        ) : (
          <Space direction="vertical" size={12} style={{ width: '100%', marginTop: 8 }}>
            {node.evidence.map((item, index) => (
              <div
                className="node-evidence-section__item"
                key={`${item.chunk_id}-${index}`}
                style={{
                  borderLeft: '3px solid #1677ff',
                  paddingLeft: 12,
                  background: 'rgba(0,0,0,0.02)',
                  padding: '8px 44px 8px 12px',
                  borderRadius: 4,
                  position: 'relative',
                }}
              >
                <Text style={{ fontSize: 12 }} type="secondary">
                  {item.type === 'job_posting' ? '岗位原文 · ' : '职业标准 · '}
                  {[
                    item.source_name,
                    item.section,
                    item.page ? `第${item.page}页` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </Text>
                <Paragraph
                  style={{ marginTop: 4, marginBottom: 0, fontSize: 13 }}
                  ellipsis={{ rows: 4, expandable: true, symbol: '展开' }}
                >
                  {item.quote}
                </Paragraph>
                {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">查看公开来源</a>}
                {editable && item.type === 'job_posting' && item.posting_id && (
                  <Popconfirm
                    title="移除岗位原文依据"
                    description="仅移除此条岗位原文关联。"
                    okText="移除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => removeJobEvidence(item.posting_id as string)}
                  >
                    <Button className="node-evidence-section__remove" type="text" danger icon={<DeleteOutlined />} aria-label="移除岗位原文依据" />
                  </Popconfirm>
                )}
              </div>
            ))}
          </Space>
        )}
      </div>

    </Space>
  )
}
