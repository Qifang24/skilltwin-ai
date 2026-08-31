/** 教师端岗位市场看板：JD 原文 → 可验证统计 → 排名与趋势。 */

import { useMemo } from 'react'
import { App, Alert, Button, Card, Col, Empty, Popover, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

import { analyzeJobMarket, fetchJobMarketDashboard, toErrorMessage } from '@/services/api'
import type { DemandEvidence, SkillDemand } from '@/types/jobMarket'

const { Title, Paragraph, Text } = Typography

const TARGET_JOB = 'ai_data_annotator'

function formatMonth(iso: string): string {
  const date = new Date(iso)
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`
}

function EvidencePopover({ evidence }: { evidence: DemandEvidence[] }) {
  if (evidence.length === 0) return <Text type="secondary">暂无可回溯原文</Text>

  const content = (
    <Space orientation="vertical" size={12} style={{ maxWidth: 460 }}>
      {evidence.map((item) => (
        <div key={item.posting_id}>
          <Space size={6} wrap>
            <Text strong>{item.title}</Text>
            <Tag color={item.data_flag === 'REAL' ? 'green' : 'orange'}>
              {item.data_flag}
            </Tag>
            <Text type="secondary">{formatDate(item.posted_at)}</Text>
          </Space>
          <Paragraph style={{ margin: '6px 0' }}>
            “{item.evidence_span}”
          </Paragraph>
          {item.source_url ? (
            <a href={item.source_url} target="_blank" rel="noreferrer">
              查看公开来源{item.source_name ? `：${item.source_name}` : ''}
            </a>
          ) : (
            <Text type="secondary">未提供公开来源链接</Text>
          )}
        </div>
      ))}
    </Space>
  )

  return (
    <Popover content={content} title="JD 原文证据（最多展示 5 条）" trigger="click">
      <Button size="small" type="link">查看 {evidence.length} 条原文</Button>
    </Popover>
  )
}

export function JobMarketDashboard() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const dashboardQuery = useQuery({
    queryKey: ['job-market-dashboard', TARGET_JOB],
    queryFn: () => fetchJobMarketDashboard(TARGET_JOB, { top_n: 10 }),
  })
  const analyze = useMutation({
    mutationFn: () => analyzeJobMarket(TARGET_JOB),
    onSuccess: (response) => {
      queryClient.setQueryData(['job-market-dashboard', TARGET_JOB], response.dashboard)
      message.success(`统计已更新：${response.extracted_skill_links} 个原文技能命中`)
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })

  const dashboard = dashboardQuery.data
  const analysisSampleCount = dashboard
    ? (dashboard.data_quality.real_postings || dashboard.data_quality.total_postings)
    : 0
  const rankingOption = useMemo<EChartsOption>(() => ({
    grid: { left: 116, right: 40, top: 18, bottom: 20 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (value) => `${value}%`,
    },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: {
      type: 'category',
      data: [...(dashboard?.ranking ?? [])].reverse().map((item) => item.skill_name ?? item.skill_code),
    },
    series: [{
      type: 'bar',
      data: [...(dashboard?.ranking ?? [])].reverse().map((item) => Math.round(item.frequency * 1000) / 10),
      itemStyle: { color: '#1677ff', borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', formatter: '{c}%' },
    }],
  }), [dashboard?.ranking])

  const trendOption = useMemo<EChartsOption>(() => {
    const months = [...new Set((dashboard?.trends ?? []).flatMap((series) =>
      series.points.map((point) => formatMonth(point.window_start)),
    ))].sort()
    return {
      tooltip: { trigger: 'axis', valueFormatter: (value) => `${value}%` },
      legend: { top: 0 },
      grid: { left: 48, right: 24, top: 42, bottom: 34 },
      xAxis: { type: 'category', data: months },
      yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
      series: (dashboard?.trends ?? []).map((series) => {
        const percentages = new Map(
          series.points.map((point) => [formatMonth(point.window_start), Math.round(point.frequency * 1000) / 10]),
        )
        return {
          name: series.skill_name ?? series.skill_code,
          type: 'line',
          smooth: true,
          connectNulls: false,
          data: months.map((month) => percentages.get(month) ?? null),
        }
      }),
    }
  }, [dashboard?.trends])

  const columns = useMemo(() => [
    {
      title: '排名',
      width: 66,
      render: (_: unknown, __: SkillDemand, index: number) => index + 1,
    },
    {
      title: '技能',
      render: (_: unknown, item: SkillDemand) => (
        <Space size={6} wrap>
          <Text strong>{item.skill_name ?? item.skill_code}</Text>
          {item.category ? <Tag>{item.category}</Tag> : null}
        </Space>
      ),
    },
    {
      title: '需求频率',
      width: 130,
      render: (_: unknown, item: SkillDemand) => `${(item.frequency * 100).toFixed(1)}% (${item.posting_count}/${item.total_postings})`,
    },
    {
      title: '样本构成',
      width: 132,
      render: (_: unknown, item: SkillDemand) => (
        <Space size={4} wrap>
          <Tag color="green">REAL {item.real_posting_count}</Tag>
          {item.demo_posting_count > 0 ? <Tag color="orange">DEMO {item.demo_posting_count}</Tag> : null}
        </Space>
      ),
    },
    {
      title: '证据',
      width: 132,
      render: (_: unknown, item: SkillDemand) => <EvidencePopover evidence={item.evidence} />,
    },
  ], [])

  return (
    <Space orientation="vertical" size={24} style={{ width: '100%' }}>
      <div>
        <Title level={2} style={{ marginBottom: 4 }}>岗位需求趋势分析</Title>
        <Paragraph type="secondary">
          以已导入的公开岗位 JD 为样本，按规范技能名与别名做原文精确匹配。图表不调用 LLM，任一统计均可下钻至岗位原文。
        </Paragraph>
      </div>

      {dashboardQuery.isError ? (
        <Alert
          type="error"
          showIcon
          message="无法读取岗位市场数据"
          description={toErrorMessage(dashboardQuery.error)}
          action={<Button size="small" onClick={() => dashboardQuery.refetch()}>重试</Button>}
        />
      ) : null}

      {dashboard ? (
        <>
          {dashboard.data_quality.warnings.map((warning) => (
            <Alert
              key={warning}
              type={warning.includes('DEMO') || warning.includes('暂无') ? 'warning' : 'info'}
              showIcon
              message={warning}
            />
          ))}

          <Card
            title={`${dashboard.job_name} · 数据质量`}
            extra={(
              <Button type="primary" loading={analyze.isPending} onClick={() => analyze.mutate()}>
                {analyze.isPending ? '正在重建统计…' : '重建统计'}
              </Button>
            )}
          >
            <Row gutter={[16, 16]}>
              <Col xs={12} md={6}><Statistic title="统计样本" value={analysisSampleCount} suffix="条" /></Col>
              <Col xs={12} md={6}><Statistic title="真实样本" value={dashboard.data_quality.real_postings} suffix="条" /></Col>
              <Col xs={12} md={6}><Statistic title="技能抽取覆盖" value={dashboard.data_quality.extraction_coverage * 100} precision={1} suffix="%" /></Col>
              <Col xs={12} md={6}><Statistic title="最近发布时间" value={formatDate(dashboard.data_quality.latest_posted_at)} /></Col>
            </Row>
            <Paragraph type="secondary" style={{ margin: '16px 0 0' }}>
              统计口径：存在真实 JD 时，仅以 REAL 样本计算；频率 = 命中该技能原文的去重 JD 数 ÷ 当前统计样本数。无发布时间的 JD 计入排名，但不计入月度趋势。
            </Paragraph>
          </Card>

          {dashboard.data_quality.total_postings === 0 ? (
            <Card>
              <Empty description="暂无可分析岗位样本">
                <Paragraph type="secondary" style={{ maxWidth: 560, margin: '16px auto' }}>
                  请先使用脱敏后的、合法公开 JD 导入数据；模板位于 <Text code>data/seed/job_postings_TEMPLATE.json</Text>。DEMO 数据仅可用于本地管线验收，不可作为行业结论。
                </Paragraph>
                <Text code>python scripts/import_postings.py --file data/seed/你的岗位数据.json</Text>
              </Empty>
            </Card>
          ) : (
            <>
              <Row gutter={[24, 24]}>
                <Col xs={24} lg={12}>
                  <Card title="热门技能排名" extra={<Text type="secondary">样本 N={analysisSampleCount}</Text>}>
                    <ReactECharts option={rankingOption} style={{ height: 340 }} notMerge lazyUpdate />
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="月度技能需求趋势" extra={<Text type="secondary">缺少发布时间的样本不计入</Text>}>
                    {dashboard.trends.length > 0 ? (
                      <ReactECharts option={trendOption} style={{ height: 340 }} notMerge lazyUpdate />
                    ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无带发布时间的趋势样本" />}
                  </Card>
                </Col>
              </Row>

              <Card title="排名明细与原文证据">
                <Table<SkillDemand>
                  rowKey="skill_code"
                  size="middle"
                  loading={dashboardQuery.isLoading}
                  columns={columns}
                  dataSource={dashboard.ranking}
                  pagination={false}
                  scroll={{ x: 740 }}
                  locale={{ emptyText: '未在 JD 原文中匹配到规范技能，请补充技能别名后重建统计。' }}
                />
              </Card>
            </>
          )}
        </>
      ) : null}
    </Space>
  )
}
