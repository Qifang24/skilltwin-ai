/** 教师端岗位市场看板：JD 原文 → 可验证统计 → 排名与趋势。 */

import { useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { App, Alert, Button, Card, Checkbox, Col, DatePicker, Empty, Input, Popover, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { analyzeJobMarket, fetchJobMarketDashboard, toErrorMessage } from '@/services/api'
import type { DemandEvidence, SkillDemand } from '@/types/jobMarket'

const { Title, Paragraph, Text } = Typography

const CATEGORY_LABELS: Record<string, string> = {
  annotation: '数据标注',
  data: '数据处理',
  soft: '职业素养',
  quality: '质量管理',
  tool: '工具应用',
  programming: '编程开发',
  ai_theory: 'AI 基础',
}
type MarketFilters = { city?: string; source?: string; title?: string; posted_from?: string; posted_to?: string }

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
    <div className="market-evidence-list">
      {evidence.map((item) => (
        <article className="market-evidence-item" key={item.posting_id}>
          <header>
            <Text strong>{item.title}</Text>
            <span className="market-evidence-item__meta">
              <Tag color={item.data_flag === 'REAL' ? 'green' : 'orange'}>{item.data_flag}</Tag>
              <Text type="secondary">{formatDate(item.posted_at)}</Text>
            </span>
          </header>
          <div className="market-evidence-item__quote">{item.evidence_span}</div>
          {item.source_url ? (
            <a href={item.source_url} target="_blank" rel="noreferrer">
              查看来源{item.source_name ? ` · ${item.source_name}` : ''} ↗
            </a>
          ) : (
            <Text type="secondary">未提供公开来源链接</Text>
          )}
        </article>
      ))}
    </div>
  )

  return (
    <Popover overlayClassName="market-evidence-popover" content={content} title="JD 原文证据 · 最多展示 5 条" trigger="click">
      <Button size="small" type="link">查看 {evidence.length} 条原文</Button>
    </Popover>
  )
}

export function JobMarketDashboard() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [search] = useSearchParams()
  const jobId = search.get('job_id') ?? ''
  const queryClient = useQueryClient()
  const [draftFilters, setDraftFilters] = useState<MarketFilters>({})
  const [filters, setFilters] = useState<MarketFilters>({})
  const dashboardQuery = useQuery({
    queryKey: ['job-market-dashboard', jobId, filters],
    queryFn: () => fetchJobMarketDashboard(jobId, { top_n: 10, ...filters }),
    enabled: Boolean(jobId),
  })
  const analyze = useMutation({
    mutationFn: () => analyzeJobMarket(jobId),
    onSuccess: (response) => {
      queryClient.setQueriesData({ queryKey: ['job-market-dashboard', jobId] }, response.dashboard)
      message.success(`统计已更新：${response.extracted_skill_links} 个原文技能命中`)
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })

  const dashboard = dashboardQuery.data
  const [selectedSkillCodes, setSelectedSkillCodes] = useState<string[] | null>(null)
  const [teachingGoal, setTeachingGoal] = useState('')
  const analysisSampleCount = dashboard
    ? (dashboard.data_quality.real_postings || dashboard.data_quality.total_postings)
    : 0
  const focusSkills = (dashboard?.ranking ?? [])
    .filter((item) => item.real_posting_count > 0 || item.posting_count > 0)
    .slice(0, 3)
  const defaultSkillCodes = focusSkills.map((skill) => skill.skill_code)
  const effectiveSkillCodes = selectedSkillCodes ?? defaultSkillCodes
  const selectedSkills = (dashboard?.ranking ?? []).filter((skill) =>
    effectiveSkillCodes.includes(skill.skill_code),
  )
  const graphFocus = [
    selectedSkills.length > 0 ? `优先围绕以下岗位能力构建图谱：${selectedSkills.map((skill) => skill.skill_name ?? skill.skill_code).join('、')}。` : '',
    teachingGoal.trim() ? `本次实训教学目标：${teachingGoal.trim()}。` : '',
  ].filter(Boolean).join('\n')
  const handoffToGraph = () => {
    if (selectedSkills.length === 0) {
      message.warning('请至少选择一项要纳入能力图谱的岗位能力')
      return
    }
    navigate('/teacher/graphs', {
      state: {
        focus: graphFocus,
        selectedSkillCodes: selectedSkills.map((skill) => skill.skill_code),
        selectedSkillNames: selectedSkills.map((skill) => skill.skill_name ?? skill.skill_code),
        teachingGoal: teachingGoal.trim(),
      },
    })
  }
  const applyFilters = () => {
    const next = Object.fromEntries(Object.entries(draftFilters).filter(([, value]) => Boolean(value))) as MarketFilters
    setFilters(next)
    setSelectedSkillCodes(null)
  }
  const resetFilters = () => {
    setDraftFilters({})
    setFilters({})
    setSelectedSkillCodes(null)
  }
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
          {item.category ? <Tag>{CATEGORY_LABELS[item.category] ?? item.category}</Tag> : null}
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
    <Space className="market-dashboard" orientation="vertical" size={16} style={{ width: '100%' }}>
      <div className="market-dashboard__heading">
        <Button className="market-dashboard__back" onClick={() => navigate('/teacher')}>← 返回教师端</Button>
        <Title level={2} style={{ marginBottom: 4 }}>岗位需求趋势分析</Title>
        <Paragraph type="secondary">
          基于公开岗位 JD，识别高频技能，为实训能力图谱设计提供依据；每项结果都可回看对应的岗位原文。
        </Paragraph>
      </div>

      {!jobId ? <Empty description="请先从岗位数据导入完成页进入，或在地址中提供 job_id。" image={Empty.PRESENTED_IMAGE_SIMPLE}><Button type="primary" onClick={() => navigate('/admin/job-data')}>导入岗位数据</Button></Empty> : null}

      {jobId ? <>

      <Card
        size="small"
        className="market-filter-panel"
        title="筛选岗位样本"
        extra={<Space size={8}><Button size="small" onClick={resetFilters}>清除筛选</Button><Button size="small" type="primary" onClick={applyFilters}>应用筛选</Button></Space>}
      >
        <Row gutter={[10, 10]}>
          <Col xs={24} sm={12} lg={5}><Input value={draftFilters.title} onChange={(event) => setDraftFilters((current) => ({ ...current, title: event.target.value }))} placeholder="岗位名称，如 AI 训练师" /></Col>
          <Col xs={24} sm={12} lg={4}><Input value={draftFilters.city} onChange={(event) => setDraftFilters((current) => ({ ...current, city: event.target.value }))} placeholder="城市，如 杭州" /></Col>
          <Col xs={24} sm={12} lg={5}><Input value={draftFilters.source} onChange={(event) => setDraftFilters((current) => ({ ...current, source: event.target.value }))} placeholder="来源，如 就业网" /></Col>
          <Col xs={24} sm={12} lg={10}>
            <DatePicker.RangePicker
              style={{ width: '100%' }}
              placeholder={['发布日期从', '发布日期至']}
              value={draftFilters.posted_from && draftFilters.posted_to ? [dayjs(draftFilters.posted_from), dayjs(draftFilters.posted_to)] : null}
              onChange={(range) => setDraftFilters((current) => ({
                ...current,
                posted_from: range?.[0]?.startOf('day').toISOString(),
                posted_to: range?.[1]?.endOf('day').toISOString(),
              }))}
            />
          </Col>
        </Row>
        <Text type="secondary">筛选会同时更新样本数、技能排名、趋势图与可带入图谱的能力清单。</Text>
      </Card>

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
          <Card
            className="market-dashboard__overview"
            title="样本与数据质量"
            extra={(
              <Button type="primary" loading={analyze.isPending} onClick={() => analyze.mutate()}>
                {analyze.isPending ? '正在重建统计…' : '重建统计'}
              </Button>
            )}
          >
            <Row gutter={[8, 8]}>
              <Col xs={12} md={6}><Statistic title="统计样本" value={analysisSampleCount} suffix="条" /></Col>
              <Col xs={12} md={6}><Statistic title="真实样本" value={dashboard.data_quality.real_postings} suffix="条" /></Col>
              <Col xs={12} md={6}><Statistic title="技能抽取覆盖" value={dashboard.data_quality.extraction_coverage * 100} precision={1} suffix="%" /></Col>
              <Col xs={12} md={6}><Statistic title="最近发布时间" value={formatDate(dashboard.data_quality.latest_posted_at)} /></Col>
            </Row>
            <Paragraph type="secondary" style={{ margin: '7px 0 0' }}>
              统计口径：存在真实 JD 时，仅以 REAL 样本计算；频率 = 命中该技能原文的去重 JD 数 ÷ 当前统计样本数。无发布时间的 JD 计入排名，但不计入月度趋势。
            </Paragraph>
            {dashboard.data_quality.warnings.length > 0 ? (
              <div className="market-quality-notes">
                <Text strong>数据质量说明</Text>
                <ul>{dashboard.data_quality.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </div>
            ) : null}
          </Card>

          {focusSkills.length > 0 && (
            <Card
              className="market-recommendation"
              title="本次实训优先培养的能力"
              extra={<Button type="primary" onClick={handoffToGraph}>带入图谱设计 →</Button>}
            >
              <Paragraph type="secondary" className="market-recommendation__intro">
                以下展示频率最高的三项能力；更多能力可在下方完整排名中勾选，再一并带入图谱设计。
              </Paragraph>
              <Row gutter={[12, 12]}>
                {focusSkills.map((skill, index) => (
                  <Col xs={24} md={8} key={skill.skill_code}>
                    <div className="market-recommendation__skill">
                      <div className="market-priority-block"><span>优先级</span><b>0{index + 1}</b></div>
                      <div className="market-recommendation__skill-copy">
                        <Checkbox
                          checked={effectiveSkillCodes.includes(skill.skill_code)}
                          onChange={(event) => setSelectedSkillCodes((current) => {
                            const selected = current ?? defaultSkillCodes
                            return event.target.checked
                              ? [...selected, skill.skill_code]
                              : selected.filter((code) => code !== skill.skill_code)
                          })}
                        >纳入本次图谱</Checkbox>
                        <Text strong>{skill.skill_name ?? skill.skill_code}</Text>
                        <Text type="secondary">{(skill.frequency * 100).toFixed(1)}% JD 提及 · {skill.real_posting_count} 条真实样本</Text>
                      </div>
                      <EvidencePopover evidence={skill.evidence} />
                    </div>
                  </Col>
                ))}
              </Row>
              <div className="market-decision-panel">
                <div>
                  <Text strong>本次实训教学目标</Text>
                  <Text type="secondary">填写后会作为图谱生成时的侧重点。</Text>
                </div>
                <Input
                  value={teachingGoal}
                  onChange={(event) => setTeachingGoal(event.target.value)}
                  maxLength={80}
                  placeholder="例如：培养学生依据规范完成图像标注与质量复核的能力"
                />
                <Text className="market-decision-panel__count">已选择 {selectedSkills.length} 项能力</Text>
              </div>
            </Card>
          )}

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
              <Row className="market-charts" gutter={[24, 24]}>
                <Col xs={24} lg={12}>
                  <Card className="market-chart-card market-chart-card--ranking" title="热门技能排名" extra={<Text type="secondary">样本 N={analysisSampleCount}</Text>}>
                    <ReactECharts option={rankingOption} style={{ height: 380 }} notMerge lazyUpdate />
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card className="market-chart-card market-chart-card--trend" title="月度技能需求趋势" extra={<Text type="secondary">缺少发布时间的样本不计入</Text>}>
                    {dashboard.trends.length > 0 ? (
                      <ReactECharts option={trendOption} style={{ height: 380 }} notMerge lazyUpdate />
                    ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无带发布时间的趋势样本" />}
                  </Card>
                </Col>
              </Row>

              <Card className="market-ranking-table" title="排名明细与原文证据">
                <Table<SkillDemand>
                  rowKey="skill_code"
                  size="middle"
                  loading={dashboardQuery.isLoading}
                  rowSelection={{
                    selectedRowKeys: effectiveSkillCodes,
                    onChange: (keys) => setSelectedSkillCodes(keys.map(String)),
                    columnTitle: '纳入图谱',
                    columnWidth: 106,
                  }}
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
      </> : null}
    </Space>
  )
}
