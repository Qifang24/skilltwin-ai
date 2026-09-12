import { Alert, App, Button, Card, Empty, Skeleton, Space, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { LearningPathTimeline } from '@/components/LearningPathTimeline'
import { PageHero } from '@/components/PageHero'
import {
  fetchGap,
  fetchLatestLearningPath,
  generateLearningPath,
  startLearningPathRetest,
  toErrorMessage,
  updateLearningPathItem,
} from '@/services/api'
import type { PathStatus } from '@/types/learning'

const { Text } = Typography
const TARGET_JOB = 'ai_data_annotator'

/** 学生 Step 03：诊断后生成、执行并复测个性化学习路径。 */
export function StudentLearningPathPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const studentId = searchParams.get('student')

  const gapQuery = useQuery({
    queryKey: ['gap', studentId, TARGET_JOB],
    queryFn: () => fetchGap(studentId!, TARGET_JOB),
    enabled: Boolean(studentId),
    retry: false,
  })
  const pathQuery = useQuery({
    queryKey: ['learning-path', studentId, TARGET_JOB],
    queryFn: () => fetchLatestLearningPath(studentId!, TARGET_JOB),
    enabled: Boolean(studentId),
    retry: false,
  })
  const hasMeasuredGap = (gapQuery.data?.gaps ?? []).some((gap) => !gap.untested && gap.gap > 5)

  const generatePath = useMutation({
    mutationFn: () => generateLearningPath(studentId!, TARGET_JOB, 4),
    onSuccess: (generated) => {
      queryClient.setQueryData(['learning-path', studentId, TARGET_JOB], generated.path)
      message.success('已生成个性化学习路径')
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })
  const startRetest = useMutation({
    mutationFn: (itemId: string) => startLearningPathRetest(studentId!, itemId, 16),
    onSuccess: (started) => navigate(`/student/assessments/${started.assessment_id}`),
    onError: (error) => message.error(toErrorMessage(error)),
  })
  const updateItem = useMutation({
    mutationFn: ({ itemId, status }: { itemId: string; status: PathStatus }) => updateLearningPathItem(studentId!, itemId, status),
    onSuccess: (path) => {
      queryClient.setQueryData(['learning-path', studentId, TARGET_JOB], path)
      message.success('学习进度已更新')
    },
    onError: (error) => message.error(toErrorMessage(error)),
  })

  return (
    <Space className="student-workspace" orientation="vertical" size={14} style={{ width: '100%' }}>
      <PageHero
        eyebrow="STEP 03 · 个性化学习"
        title="按学习路径练习"
        description="系统会根据你的能力诊断结果，安排优先练习的技能与实训任务。"
        actions={<Button type="primary" onClick={() => navigate(`/student/diagnosis?student=${encodeURIComponent(studentId ?? '')}`)}>← 返回上一步</Button>}
      />

      <Card className="student-learning-path-page">
        {!studentId ? (
          <Empty description="请先选择学习档案并完成能力诊断">
            <Button type="primary" onClick={() => navigate('/student')}>返回学习首页</Button>
          </Empty>
        ) : gapQuery.isLoading || pathQuery.isLoading ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : pathQuery.isError ? (
          <Alert type="error" showIcon title="无法读取学习路径" description={toErrorMessage(pathQuery.error)} />
        ) : pathQuery.data ? (
          <LearningPathTimeline
            path={pathQuery.data}
            regenerating={generatePath.isPending}
            retestPending={startRetest.isPending}
            updatingItemId={updateItem.isPending ? updateItem.variables?.itemId : undefined}
            onRegenerate={() => generatePath.mutate()}
            onRetest={(itemId) => startRetest.mutate(itemId)}
            onItemStatus={(itemId, status) => updateItem.mutate({ itemId, status })}
          />
        ) : (
          <Empty
            description={hasMeasuredGap ? '系统将根据你的能力差距生成学习路径。' : '当前没有需要补齐的已测评技能，请先补充诊断。'}
          >
            <Button type="primary" size="large" loading={generatePath.isPending} disabled={!hasMeasuredGap} onClick={() => generatePath.mutate()}>
              生成个性化学习
            </Button>
          </Empty>
        )}
        {studentId && gapQuery.isError && <Text type="secondary">暂时无法读取诊断结果，请返回 Step 02 后重试。</Text>}
      </Card>
    </Space>
  )
}
