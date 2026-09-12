import { Alert, Button, Card, Empty, Space, Table, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { PageHero } from '@/components/PageHero'

import { fetchCurriculumGap, toErrorMessage } from '@/services/api'
import type { CurriculumSkillGap } from '@/types/curriculum'

const { Paragraph, Text } = Typography
const TARGET_JOB = 'ai_data_annotator'
const STATUS: Record<CurriculumSkillGap['status'], [string, string]> = { unmapped: ['red', '未映射'], introduced: ['gold', '已提及'], practice: ['green', '实践目标'] }

export function CurriculumGapDashboard() {
  const navigate = useNavigate()
  const query = useQuery({ queryKey: ['curriculum-gap', TARGET_JOB], queryFn: () => fetchCurriculumGap(TARGET_JOB) })
  const data = query.data
  return <Space className="curriculum-page" orientation="vertical" size={24} style={{ width: '100%' }}>
    <PageHero
      eyebrow={'\u8bfe\u7a0b\u5bf9\u6807'}
      title={'\u8bfe\u7a0b\u8986\u76d6\u4e0e\u5c97\u4f4d\u80fd\u529b\u5bf9\u6807'}
      description={'\u67e5\u770b\u8bfe\u7a0b\u5bf9\u5c97\u4f4d\u80fd\u529b\u7684\u8986\u76d6\u60c5\u51b5\u4e0e\u539f\u6587\u8bc1\u636e\u3002'}
      actions={<Button type="primary" onClick={() => navigate('/admin')}>{'\u2190 \u8fd4\u56de\u7ba1\u7406\u7aef'}</Button>}
    />
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
