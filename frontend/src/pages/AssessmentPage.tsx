/**
 * 答题页。
 *
 * 开考前先把统计效力提示摆出来 —— 「本卷 16 题覆盖 14 项技能，
 * 不宜作为精确评价」这句话必须说在学生做题之前，
 * 而不是做完 16 题才告诉他结果不可信。
 */

import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Progress,
  Radio,
  Result,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { fetchAssessment, submitAssessment, toErrorMessage } from '@/services/api'
import { ITEM_TYPE_LABELS } from '@/types/student'

const { Title, Paragraph, Text } = Typography

export function AssessmentPage() {
  const { assessmentId = '' } = useParams()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [answers, setAnswers] = useState<Record<string, string[]>>({})

  const { data, isLoading, error } = useQuery({
    queryKey: ['assessment', assessmentId],
    queryFn: () => fetchAssessment(assessmentId),
    enabled: Boolean(assessmentId),
  })

  const submit = useMutation({
    mutationFn: () =>
      submitAssessment(
        assessmentId,
        (data?.items ?? []).map((item) => ({
          item_id: item.id,
          response: answers[item.id] ?? [],
        })),
      ),
    onSuccess: (result) => {
      const inherited = result.inherited_skill_codes.length
        ? `，并安全继承 ${result.inherited_skill_codes.length} 项未复测技能`
        : ''
      const studentId = data?.student_id ?? ''
      const pathMessage = result.learning_path_update?.message
        ? `；${result.learning_path_update.message}`
        : ''
      message.success(
        `已交卷：答对 ${result.correct_count}/${result.total_count}${inherited}${pathMessage}`,
      )
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ['profile', studentId] }),
        queryClient.invalidateQueries({ queryKey: ['gap', studentId] }),
        queryClient.invalidateQueries({ queryKey: ['learning-path', studentId] }),
      ])
      navigate(`/student?student=${encodeURIComponent(studentId)}`)
    },
    onError: (e) => message.error(toErrorMessage(e)),
  })

  const answeredCount = useMemo(
    () => Object.values(answers).filter((v) => v.length > 0).length,
    [answers],
  )

  if (isLoading) return <Skeleton active paragraph={{ rows: 12 }} />
  if (error || !data) {
    return (
      <Result
        status="error"
        title="无法加载试卷"
        subTitle={toErrorMessage(error)}
        extra={
          <Link to="/student">
            <Button type="primary">返回</Button>
          </Link>
        }
      />
    )
  }

  if (data.status === 'scored') {
    return (
      <Result
        status="success"
        title="本卷已完成"
        subTitle="能力画像已生成，可在学习中心查看。"
        extra={
          <Link to={`/student?student=${encodeURIComponent(data.student_id)}`}>
            <Button type="primary">查看能力画像</Button>
          </Link>
        }
      />
    )
  }

  const total = data.items.length
  const isRetest = data.type === 'retest'

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          {isRetest ? '岗位能力复测' : '岗位能力诊断'}
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          共 {total} 题，均为客观题。
          {isRetest
            ? '本次使用岗位综合题库；测到的技能将更新，未覆盖维度会继承上一份画像。'
            : '结果用于定位你的能力薄弱环节，不计入成绩。'}
        </Paragraph>
      </div>

      {/* 统计效力提示必须在做题之前出现 */}
      {data.notes.map((note) => (
        <Alert
          key={note}
          type="warning"
          showIcon
          title="关于本次测评的说明"
          description={note}
        />
      ))}

      <Card size="small">
        <Space orientation="vertical" size={6} style={{ width: '100%' }}>
          <Text>
            已作答 {answeredCount} / {total}
          </Text>
          <Progress
            percent={Math.round((answeredCount / Math.max(total, 1)) * 100)}
            size="small"
            status={answeredCount === total ? 'success' : 'active'}
          />
        </Space>
      </Card>

      {data.items.map((item, index) => (
        <Card
          key={item.id}
          size="small"
          title={
            <Space size={8}>
              <Text strong>第 {index + 1} 题</Text>
              <Tag>{ITEM_TYPE_LABELS[item.item_type]}</Tag>
              {item.skill_codes.map((code) => (
                <Tag key={code} color="magenta" style={{ fontSize: 11 }}>
                  {code}
                </Tag>
              ))}
            </Space>
          }
        >
          <Paragraph>{item.stem}</Paragraph>

          {item.item_type === 'judge' ? (
            <Radio.Group
              value={answers[item.id]?.[0]}
              onChange={(e) =>
                setAnswers((prev) => ({ ...prev, [item.id]: [e.target.value] }))
              }
            >
              <Radio value="true">正确</Radio>
              <Radio value="false">错误</Radio>
            </Radio.Group>
          ) : item.item_type === 'multi' ? (
            <Checkbox.Group
              value={answers[item.id] ?? []}
              onChange={(values) =>
                setAnswers((prev) => ({ ...prev, [item.id]: values as string[] }))
              }
            >
              <Space orientation="vertical">
                {item.options.map((option) => (
                  <Checkbox key={option.key} value={option.key}>
                    {option.key}. {option.text}
                  </Checkbox>
                ))}
              </Space>
            </Checkbox.Group>
          ) : (
            <Radio.Group
              value={answers[item.id]?.[0]}
              onChange={(e) =>
                setAnswers((prev) => ({ ...prev, [item.id]: [e.target.value] }))
              }
            >
              <Space orientation="vertical">
                {item.options.map((option) => (
                  <Radio key={option.key} value={option.key}>
                    {option.key}. {option.text}
                  </Radio>
                ))}
              </Space>
            </Radio.Group>
          )}
        </Card>
      ))}

      <Card size="small">
        <Space orientation="vertical" size={10} style={{ width: '100%' }}>
          {answeredCount < total && (
            <Text type="warning">
              还有 {total - answeredCount} 题未作答，未作答按错误计分。
            </Text>
          )}
          <Button
            type="primary"
            size="large"
            block
            loading={submit.isPending}
            disabled={answeredCount === 0}
            onClick={() => submit.mutate()}
          >
            {isRetest ? '交卷并更新能力画像' : '交卷并生成能力画像'}
          </Button>
        </Space>
      </Card>
    </Space>
  )
}
