import { Alert, Card, Empty, List, Space, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { fetchCurriculumOptimization, toErrorMessage } from '@/services/api'

const { Title, Paragraph, Text } = Typography
export function CurriculumOptimization() {
  const query = useQuery({ queryKey: ['curriculum-optimization', 'ai_data_annotator'], queryFn: () => fetchCurriculumOptimization('ai_data_annotator') })
  const data = query.data
  return <Space orientation="vertical" size={24} style={{ width: '100%' }}>
    <div><Title level={2}>人才培养方案优化建议</Title><Paragraph type="secondary">建议由可靠岗位需求频率与课程原文覆盖证据确定性生成，不使用 LLM 编造结论。</Paragraph></div>
    {query.isError ? <Alert type="error" showIcon title="无法读取优化建议" description={toErrorMessage(query.error)} /> : null}
    {data ? <>{data.warnings.map((warning) => <Alert key={warning} type="warning" showIcon title={warning} />)}
      <Card title="建议优先级">
        {data.recommendations.length ? <List dataSource={data.recommendations} renderItem={(item) => <List.Item><List.Item.Meta title={<Space><Text strong>{item.title}</Text><Tag color="red">优先级 {item.priority_score}</Tag></Space>} description={<Space orientation="vertical" size={4}><Text>{item.suggestion}</Text><Text type="secondary">{item.reasoning_summary}</Text>{item.course_evidence.map((e) => <Text key={e.course_id} type="secondary">课程证据：{e.course_name} · “{e.evidence_quote}”</Text>)}</Space>} /></List.Item>} /> : <Empty description="当前没有可排序的优化建议" />}
      </Card>
    </> : null}
  </Space>
}
