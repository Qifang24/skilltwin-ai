/**
 * 系统状态卡片。
 *
 * 数据全部来自后端 /api/v1/health —— 这是「前端零硬编码」原则的第一个落点，
 * 也是排查环境问题最快的入口（模型没配、GPU 没识别、向量库没就绪都能一眼看到）。
 */

import { Alert, Card, Skeleton, Space, Tag } from 'antd'
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
    <Card className="system-status-card" bordered={false}>
      <div className="system-status-card__overview">
        <div>
          <span className="system-status-card__eyebrow">SYSTEM HEALTH</span>
          <h2>{healthy ? '系统运行正常' : '系统需要检查'}</h2>
          <p>
            {data.app} v{data.version} · {DEMO_MODE_LABELS[data.demo_mode] ?? data.demo_mode}
          </p>
        </div>
        <div className={`system-status-card__summary ${healthy ? 'is-healthy' : 'is-warning'}`}>
          <span className="system-status-card__pulse" />
          <strong>{healthy ? '全部就绪' : '部分未就绪'}</strong>
          <small>{data.components.filter((component) => component.ok).length} / {data.components.length} 核心服务可用</small>
        </div>
      </div>

      <div className="system-status-card__grid">
        {data.components.map((component) => (
          <div className="system-status-card__item" key={component.name}>
            <div className="system-status-card__item-title">
              <span className={component.ok ? 'is-ok' : 'is-error'} />
              {COMPONENT_LABELS[component.name] ?? component.name}
            </div>
            <p>{component.detail}</p>
            <Tag color={component.ok ? 'success' : 'error'}>
              {component.ok ? '运行正常' : '需要处理'}
            </Tag>
          </div>
        ))}
      </div>
    </Card>
  )
}
