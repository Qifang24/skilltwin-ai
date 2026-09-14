import {
  Alert,
  Button,
  Card,
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
    <Card size="small" className={`learning-path-item learning-path-item--${item.item_type}`}>
      <Flex justify="space-between" align="flex-start" gap={12} wrap>
        <Space orientation="vertical" size={3} style={{ flex: 1 }}>
          <Space size={6} wrap>
            <Tag className={`learning-path-item__type learning-path-item__type--${item.item_type}`}>
              {PATH_ITEM_LABELS[item.item_type]}
            </Tag>
            <Text strong>{item.title}</Text>
            <Tag color={PATH_STATUS_COLORS[item.status]} className="learning-path-item__status">
              {PATH_STATUS_LABELS[item.status]}
            </Tag>
          </Space>
          <Space orientation="vertical" size={2}>
            {item.description ? (
              <Text type="secondary" style={{ whiteSpace: 'pre-line' }}>
                {item.description}
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
    </Card>
  )
}

interface LearningPathTimelineProps {
  path: LearningPath
  regenerating: boolean
  retestPending: boolean
  updatingItemId?: string
  onRegenerate: () => void
  onRetest: (itemId: string) => void
  onItemStatus: (itemId: string, status: PathStatus) => void
}

export function LearningPathTimeline({
  path,
  regenerating,
  retestPending,
  updatingItemId,
  onRegenerate,
  onRetest,
  onItemStatus,
}: LearningPathTimelineProps) {
  const currentPhase = path.phases.find((phase) => phase.status === 'active') ?? path.phases[0]
  const nextItem = currentPhase?.items.find((item) => item.status === 'active') ?? currentPhase?.items[0]

  return (
    <Card
      title="我的个性化学习路径"
      extra={
        <Space>
          <Button type="primary" className="learning-path-regenerate" loading={regenerating} onClick={onRegenerate}>
            重新生成路径
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        {path.status === 'archived' ? (
          <Alert
            type="info"
            showIcon
            title="这是历史学习路径"
            description="该版本已归档，只能查看记录；请使用最新能力画像生成或查看当前路径。"
          />
        ) : null}

        {currentPhase && nextItem ? (
          <Card className="learning-path-next-card" size="small" title="现在先做什么">
            <Space orientation="vertical" size={5}>
              <Space size={8} wrap>
                <Tag color="blue">第 {currentPhase.order_index + 1} 阶段</Tag>
                <Tag className={`learning-path-item__type learning-path-item__type--${nextItem.item_type}`}>
                  {PATH_ITEM_LABELS[nextItem.item_type]}
                </Tag>
              </Space>
              <Text strong>{nextItem.title}</Text>
              {nextItem.description ? (
                <div className="learning-path-next-card__description">
                  {nextItem.description
                    .split(/(?=\s*\d+\.\s)/)
                    .filter(Boolean)
                    .map((line, index) => (
                      <Text key={`${index}-${line.slice(0, 12)}`} className="learning-path-next-card__line">
                        {line.trim()}
                      </Text>
                    ))}
                </div>
              ) : null}
            </Space>
          </Card>
        ) : null}

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

        <Timeline
          items={path.phases.map((phase) => ({
            color: phase.status === 'completed' ? 'green' : 'blue',
            content: (
              <Card
                key={phase.id}
                size="small"
                title={`第 ${phase.order_index + 1} 阶段 · ${phase.title}`}
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
                    <Paragraph ellipsis={{ rows: 2, expandable: 'collapsible', symbol: '查看阶段说明' }} style={{ marginBottom: 0 }}>
                      {phase.description}
                    </Paragraph>
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
      </Space>
    </Card>
  )
}
