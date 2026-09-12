import { Alert, Button, Card, Empty, List, Space, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { PageHero } from '@/components/PageHero'
import { fetchCurriculumOptimization, toErrorMessage } from '@/services/api'

const { Text } = Typography
export function CurriculumOptimization() {
  const navigate = useNavigate()
  const query = useQuery({ queryKey: ['curriculum-optimization', 'ai_data_annotator'], queryFn: () => fetchCurriculumOptimization('ai_data_annotator') })
  const data = query.data
  return <Space className="curriculum-page" orientation="vertical" size={24} style={{ width: '100%' }}>
    <PageHero
      eyebrow={'\u57f9\u517b\u65b9\u6848\u4f18\u5316'}
      title={'\u57f9\u517b\u65b9\u6848\u4f18\u5316\u5efa\u8bae'}
      description={'\u57fa\u4e8e\u5c97\u4f4d\u9700\u6c42\u4e0e\u8bfe\u7a0b\u8986\u76d6\u7f3a\u53e3\u751f\u6210\u4f18\u5316\u5efa\u8bae\u3002'}
      actions={<Button type="primary" onClick={() => navigate('/admin')}>{'\u2190 \u8fd4\u56de\u7ba1\u7406\u7aef'}</Button>}
    />
    {query.isError ? <Alert type="error" showIcon title="无法读取优化建议" description={toErrorMessage(query.error)} /> : null}
    {data ? <>{data.warnings.map((warning) => <Alert key={warning} type="warning" showIcon title={warning} />)}
      <Card title="建议优先级">
        {data.recommendations.length ? <List dataSource={data.recommendations} renderItem={(item) => <List.Item><List.Item.Meta title={<Space><Text strong>{item.title}</Text><Tag color="red">优先级 {item.priority_score}</Tag></Space>} description={<Space orientation="vertical" size={4}><Text>{item.suggestion}</Text><Text type="secondary">{item.reasoning_summary}</Text>{item.course_evidence.map((e) => <Text key={e.course_id} type="secondary">课程证据：{e.course_name} · “{e.evidence_quote}”</Text>)}</Space>} /></List.Item>} /> : <Empty description="当前没有可排序的优化建议" />}
      </Card>
    </> : null}
  </Space>
}
