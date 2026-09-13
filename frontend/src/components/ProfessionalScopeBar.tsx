import { Alert, Button, Card, Modal, Select, Space, Spin, Typography, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteCurriculumPlan, fetchCurriculumPlans, fetchGraphs, fetchMarketJobs, toErrorMessage } from '@/services/api'
import { useProfessionalScope } from '@/hooks/useProfessionalScope'

const { Text } = Typography
export function ProfessionalScopeBar({ requireGraph = true }: { requireGraph?: boolean }) {
  const [scope, setScope] = useProfessionalScope()
  const queryClient = useQueryClient()
  const jobs = useQuery({ queryKey: ['market-jobs'], queryFn: fetchMarketJobs })
  const plans = useQuery({ queryKey: ['curriculum-plans'], queryFn: fetchCurriculumPlans })
  const graphs = useQuery({ queryKey: ['scope-graphs', scope.jobId], queryFn: () => fetchGraphs({ job_id: scope.jobId, status: 'approved' }), enabled: Boolean(scope.jobId) })
  const removePlan = useMutation({ mutationFn: deleteCurriculumPlan, onSuccess: (_, planId) => { if (scope.planId === planId) setScope({ planId: '' }); void queryClient.invalidateQueries({ queryKey: ['curriculum-plans'] }); message.success('培养方案已删除') }, onError: (error) => message.error(toErrorMessage(error)) })
  const graphItems = graphs.data?.items ?? []
  const selectedPlan = plans.data?.find((plan) => plan.id === scope.planId)
  const confirmDeletePlan = () => {
    if (!scope.planId || !selectedPlan) return
    const planId = scope.planId
    Modal.confirm({ title: '删除当前培养方案？', content: `将删除“${selectedPlan.name}”及其课程、对标分析和优化建议，此操作不可恢复。若方案或课程已被教学任务引用，系统会阻止删除，避免证据链断开。`, okText: '删除', okButtonProps: { danger: true }, cancelText: '取消', onOk: () => removePlan.mutateAsync(planId) })
  }
  return <Card size="small" className="professional-scope-bar" title="当前专业建设范围">
    <Space wrap size="middle" style={{ width: '100%' }}>
      <Select showSearch optionFilterProp="label" aria-label="岗位" value={scope.jobId || undefined} onChange={(value) => setScope({ jobId: value, graphId: '' })} placeholder="选择岗位" loading={jobs.isLoading} style={{ minWidth: 230 }} options={(jobs.data ?? []).map((job) => ({ value: job.id, label: `${job.name} · ${job.id}` }))} />
      <Select aria-label="培养方案" value={scope.planId || undefined} onChange={(value) => setScope({ planId: value })} placeholder="选择培养方案" loading={plans.isLoading} style={{ minWidth: 210 }} options={(plans.data ?? []).map((plan) => ({ value: plan.id, label: plan.name }))} />
      <Button danger size="small" disabled={!selectedPlan || removePlan.isPending} loading={removePlan.isPending} onClick={confirmDeletePlan}>删除当前方案</Button>
      {requireGraph ? <Select aria-label="已审核能力图谱" value={scope.graphId || undefined} onChange={(value) => setScope({ graphId: value })} placeholder="选择已审核图谱" loading={graphs.isLoading} disabled={!scope.jobId} style={{ minWidth: 220 }} options={graphItems.map((graph) => ({ value: graph.id, label: graph.title ?? `图谱 v${graph.version} · ${graph.id.slice(0, 8)}` }))} /> : null}
      <Button size="small" onClick={() => { void plans.refetch(); if (scope.jobId) void graphs.refetch() }}>刷新选项</Button>
    </Space>
    {plans.isError || graphs.isError || jobs.isError ? <Alert className="professional-scope-bar__error" type="warning" showIcon title="范围选项暂时无法加载" description={toErrorMessage(plans.error ?? graphs.error ?? jobs.error)} /> : null}
    {!scope.jobId ? <Text type="secondary">先选择岗位，或从岗位数据导入完成页直接进入。</Text> : null}
    {graphs.isFetching ? <Spin size="small" /> : null}
  </Card>
}
