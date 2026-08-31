import { Alert, Card, Empty, Space, Table, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { fetchCurriculumGap, toErrorMessage } from '@/services/api'
import type { CurriculumSkillGap } from '@/types/curriculum'

const { Title, Paragraph, Text } = Typography
const TARGET_JOB = 'ai_data_annotator'
const STATUS: Record<CurriculumSkillGap['status'], [string, string]> = { unmapped: ['red', '未映射'], introduced: ['gold', '已提及'], practice: ['green', '实践目标'] }

export function CurriculumGapDashboard() {
  const query = useQuery({ queryKey: ['curriculum-gap', TARGET_JOB], queryFn: () => fetchCurriculumGap(TARGET_JOB) })
  const data = query.data
  return <Space orientation="vertical" size={24} style={{ width: '100%' }}>
    <div><Title level={2}>课程覆盖与岗位能力 Gap</Title><Paragraph type="secondary">课程映射仅基于已导入方案原文；“未映射”表示当前结构化范围内未见证据，不等同于课程未教学。</Paragraph></div>
    {query.isError ? <Alert type="error" showIcon title="无法读取课程 Gap 数据" description={toErrorMessage(query.error)} /> : null}
    {data ? <>
      {data.data_quality.warnings.map((warning) => <Alert key={warning} type="warning" showIcon title={warning} />)}
      <Card title={data.data_quality.plan_name} extra={data.data_quality.source_url ? <a href={data.data_quality.source_url} target="_blank" rel="noreferrer">查看公开方案</a> : null}>
        <Text>已结构化 {data.data_quality.course_count} 门课程，映射 {data.data_quality.mapped_skill_count} 个技能。{data.data_quality.market_is_reliable ? '岗位频率已参与排序。' : '岗位频率未参与排序。'}</Text>
      </Card>
      <Card title="技能覆盖明细"><Table<CurriculumSkillGap> rowKey="skill_code" loading={query.isLoading} dataSource={data.skills} pagination={false} scroll={{ x: 800 }} locale={{ emptyText: <Empty description="暂无可对标技能" /> }} columns={[
        { title: '技能', render: (_, row) => <Text strong>{row.skill_name}</Text> },
        { title: '课程覆盖', width: 110, render: (_, row) => <Tag color={STATUS[row.status][0]}>{STATUS[row.status][1]}</Tag> },
        { title: '岗位频率', width: 110, render: (_, row) => row.demand_frequency === null ? '未启用' : `${(row.demand_frequency * 100).toFixed(1)}%` },
        { title: '课程原文证据', render: (_, row) => row.courses.length ? row.courses.map((course) => <Paragraph key={course.course_id} style={{ margin: 0 }}><Text strong>{course.course_name}</Text>（{course.total_hours ?? '—'} 学时）：{course.evidence_quote}</Paragraph>) : <Text type="secondary">当前结构化范围内暂无证据</Text> },
        { title: '建议', render: (_, row) => row.recommendation },
      ]} /></Card>
    </> : null}
  </Space>
}
