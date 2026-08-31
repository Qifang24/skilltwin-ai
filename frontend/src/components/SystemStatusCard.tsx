/**
 * 系统状态卡片。
 *
 * 数据全部来自后端 /api/v1/health —— 这是「前端零硬编码」原则的第一个落点，
 * 也是排查环境问题最快的入口（模型没配、GPU 没识别、向量库没就绪都能一眼看到）。
 */

import { Alert, Card, Descriptions, Skeleton, Space, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { fetchHealth, toErrorMessage } from '@/services/api'
import { COMPONENT_LABELS } from '@/types/api'

const DEMO_MODE_LABELS: Record<string, string> = {
  live: '实时调用',
  record: '实时调用并录制',
  replay: '缓存回放（离线）',
}

export function SystemStatusCard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: 1,
  })

  if (isLoading) {
    return (
      <Card title="系统状态">
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    )
  }

  if (error || !data) {
    return (
      <Card title="系统状态">
        <Alert
          type="error"
          showIcon
          message="后端未连接"
          description={
            <Space direction="vertical" size={4}>
              <span>{toErrorMessage(error)}</span>
              <code>cd backend &amp;&amp; ../.venv/Scripts/python.exe -m uvicorn app.main:app --reload</code>
            </Space>
          }
        />
      </Card>
    )
  }

  const healthy = data.status === 'ok'

  return (
    <Card
      title="系统状态"
      extra={
        <Tag color={healthy ? 'success' : 'warning'}>
          {healthy ? '全部就绪' : '部分组件未就绪'}
        </Tag>
      }
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="版本">
          {data.app} v{data.version}
        </Descriptions.Item>
        <Descriptions.Item label="模型调用模式">
          {DEMO_MODE_LABELS[data.demo_mode] ?? data.demo_mode}
        </Descriptions.Item>
        {data.components.map((component) => (
          <Descriptions.Item
            key={component.name}
            label={COMPONENT_LABELS[component.name] ?? component.name}
          >
            <Space size={8} wrap>
              <Tag color={component.ok ? 'success' : 'error'}>
                {component.ok ? '正常' : '未就绪'}
              </Tag>
              <span style={{ color: 'rgba(0,0,0,0.65)' }}>{component.detail}</span>
            </Space>
          </Descriptions.Item>
        ))}
      </Descriptions>
    </Card>
  )
}
