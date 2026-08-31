import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Flex,
  Progress,
  Space,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import type {
  GenerateLearningPathResponse,
  LearningPath,
  LearningPathItem,
  PathStatus,
} from '@/types/learning'
import {
  PATH_ITEM_LABELS,
  PATH_STATUS_COLORS,
  PATH_STATUS_LABELS,
} from '@/types/learning'

const { Paragraph, Text } = Typography

const DATE_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

interface PathItemRowProps {
  item: LearningPathItem
  studentId: string
  retestPending: boolean
  pathStatus: PathStatus
  updatingItemId?: string
  onRetest: (itemId: string) => void
  onItemStatus: (itemId: string, status: PathStatus) => void
}

function PathItemRow({
  item,
  studentId,
  retestPending,
  pathStatus,
  updatingItemId,
  onRetest,
  onItemStatus,
}: PathItemRowProps) {
  const archived = pathStatus === 'archived'
  const updating = updatingItemId === item.id
  const actions: ReactNode[] = []

  if (item.item_type === 'task' && item.ref_id) {
    actions.push(
      <Link
        key="open-task"
        to={`/student/tasks/${item.ref_id}?student=${encodeURIComponent(studentId)}`}
      >
        <Button type="link" size="small">
          打开实训
        </Button>
      </Link>,
    )
  }
  if (item.item_type === 'assessment') {
    if (item.status !== 'completed') {
      actions.push(
        <Button
          key="start-retest"
          type="link"
          size="small"
          disabled={archived}
          loading={retestPending}
          onClick={() => onRetest(item.id)}
        >
          开始岗位复测
        </Button>,
      )
    }
  } else if (item.status === 'completed' || item.status === 'skipped') {
    actions.push(
      <Button
        key="reopen"
        type="link"
        size="small"
        disabled={archived}
        loading={updating}
        onClick={() => onItemStatus(item.id, 'active')}
      >
        重新打开
      </Button>,
    )
  } else {
    actions.push(
      <Button
        key="complete"
        type="link"
        size="small"
        disabled={archived}
        loading={updating}
        onClick={() => onItemStatus(item.id, 'completed')}
      >
        标记完成
      </Button>,
      <Button
        key="skip"
        type="link"
        size="small"
        disabled={archived}
        loading={updating}
        onClick={() => onItemStatus(item.id, 'skipped')}
      >
        跳过
      </Button>,
    )
  }

  return (
    <div style={{ padding: '12px 0', borderBottom: '1px solid #f0f0f0' }}>
      <Flex justify="space-between" align="flex-start" gap={12} wrap>
        <Space orientation="vertical" size={3} style={{ flex: 1 }}>
          <Space size={6} wrap>
            <Tag>{PATH_ITEM_LABELS[item.item_type]}</Tag>
            <Text>{item.title}</Text>
            {item.skill_code ? <Tag color="magenta">{item.skill_code}</Tag> : null}
            <Tag color={PATH_STATUS_COLORS[item.status]}>
              {PATH_STATUS_LABELS[item.status]}
            </Tag>
          </Space>
          <Space orientation="vertical" size={2}>
            {item.description ? (
              <Text type="secondary" style={{ whiteSpace: 'pre-line' }}>
                {item.description}
              </Text>
            ) : null}
            {item.item_type === 'task' ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                标记完成只记录学习进度；能力提升需由任务评分或复测证据确认。
              </Text>
            ) : null}
            {item.completed_at ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                完成于 {DATE_FORMATTER.format(new Date(item.completed_at))}
              </Text>
            ) : null}
          </Space>
        </Space>
        {actions.length ? <Space wrap>{actions}</Space> : null}
      </Flex>
    </div>
  )
}

interface LearningPathTimelineProps {
  path: LearningPath
  generation?: GenerateLearningPathResponse
  regenerating: boolean
  retestPending: boolean
  updatingItemId?: string
  onRegenerate: () => void
  onRetest: (itemId: string) => void
  onItemStatus: (itemId: string, status: PathStatus) => void
}

export function LearningPathTimeline({
  path,
  generation,
  regenerating,
  retestPending,
  updatingItemId,
  onRegenerate,
  onRetest,
  onItemStatus,
}: LearningPathTimelineProps) {
  const evidenceWarning =
    generation?.evidence_sufficiency === 'insufficient'
      ? '当前知识库没有为路径文案检索到足够依据；阶段顺序仍由已审核图谱、前置关系和能力 Gap 确定。'
      : null

  return (
    <Card
      title={path.title ?? '个性化学习路径'}
      extra={
        <Space>
          {path.generation_run_id ? <Tag color="blue">AI 生成文案</Tag> : null}
          <Button loading={regenerating} onClick={onRegenerate}>
            根据最新画像刷新
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        {path.warnings.map((warning) => (
          <Alert key={warning} type="warning" showIcon title={warning} />
        ))}

        {path.status === 'archived' ? (
          <Alert
            type="info"
            showIcon
            title="这是历史学习路径"
            description="该版本已归档，只能查看记录；请使用最新能力画像生成或查看当前路径。"
          />
        ) : null}

        {evidenceWarning ? (
          <Alert type="warning" showIcon title="路径文案依据不足" description={evidenceWarning} />
        ) : null}

        {generation?.reasoning_summary ? (
          <Alert
            type="info"
            showIcon
            title="生成说明"
            description={generation.reasoning_summary}
          />
        ) : null}

        <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }} bordered>
          <Descriptions.Item label="状态">
            <Tag color={PATH_STATUS_COLORS[path.status]}>
              {PATH_STATUS_LABELS[path.status]}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="阶段数">{path.phases.length}</Descriptions.Item>
          <Descriptions.Item label="排序方法">
            {path.ordering_method ?? '—'}
          </Descriptions.Item>
          <Descriptions.Item label="生成时间">
            {DATE_FORMATTER.format(new Date(path.created_at))}
          </Descriptions.Item>
        </Descriptions>

        <div>
          <Space style={{ marginBottom: 6 }}>
            <Text strong>总体进度</Text>
            <Text type="secondary">
              {path.progress.done_items}/{path.progress.total_items} 项
              {path.progress.skipped_items
                ? `（含跳过 ${path.progress.skipped_items} 项）`
                : ''}
            </Text>
          </Space>
          <Progress
            percent={path.progress.percent}
            status={path.status === 'completed' ? 'success' : 'active'}
          />
        </div>

        {path.rationale ? (
          <Paragraph style={{ marginBottom: 0 }}>{path.rationale}</Paragraph>
        ) : null}

        <Alert
          type="info"
          showIcon
          title="关于阶段复测"
          description="当前复测入口使用岗位综合题库，不是只覆盖本阶段技能的专项卷；结果会更新本次考查维度，其余维度由完整画像快照安全继承。"
        />

        <Timeline
          items={path.phases.map((phase) => ({
            color: phase.status === 'completed' ? 'green' : 'blue',
            content: (
              <Card
                key={phase.id}
                size="small"
                title={`Phase ${phase.order_index + 1} · ${phase.title}`}
                extra={
                  <Space>
                    <Tag color={PATH_STATUS_COLORS[phase.status]}>
                      {PATH_STATUS_LABELS[phase.status]}
                    </Tag>
                    {phase.est_hours ? (
                      <Text type="secondary">约 {phase.est_hours} 小时</Text>
                    ) : null}
                  </Space>
                }
              >
                <Space orientation="vertical" size={10} style={{ width: '100%' }}>
                  {phase.description ? (
                    <Paragraph style={{ marginBottom: 0 }}>{phase.description}</Paragraph>
                  ) : null}
                  <Space size={[4, 6]} wrap>
                    {phase.target_skill_codes.map((code) => (
                      <Tag key={code} color="purple">
                        {code}
                      </Tag>
                    ))}
                  </Space>
                  {phase.ordering_note ? (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      排序依据：{phase.ordering_note}
                    </Text>
                  ) : null}
                  <Progress
                    percent={phase.progress.percent}
                    size="small"
                    status={phase.status === 'completed' ? 'success' : 'active'}
                  />
                  <div>
                    {phase.items.map((item) => (
                      <PathItemRow
                        key={item.id}
                        item={item}
                        studentId={path.student_id}
                        retestPending={retestPending}
                        pathStatus={path.status}
                        updatingItemId={updatingItemId}
                        onRetest={onRetest}
                        onItemStatus={onItemStatus}
                      />
                    ))}
                  </div>
                </Space>
              </Card>
            ),
          }))}
        />

        {generation?.sources.length ? (
          <Collapse
            size="small"
            items={[
              {
                key: 'sources',
                label: `路径文案参考依据（${generation.sources.length}）`,
                children: (
                  <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                    {generation.sources.map((source, index) => (
                      <div
                        key={`${source.chunk_id ?? source.source_name ?? 'source'}-${index}`}
                        style={{ paddingBottom: 8, borderBottom: '1px solid #f0f0f0' }}
                      >
                        <Text strong>
                          {source.source_name ?? source.chunk_id ?? '知识库来源'}
                        </Text>
                        <br />
                        <Text type="secondary">
                          {[
                            source.section,
                            source.page ? `第 ${source.page} 页` : null,
                            source.quote,
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </Text>
                      </div>
                    ))}
                  </Space>
                ),
              },
            ]}
          />
        ) : null}
      </Space>
    </Card>
  )
}
