import { Button, Layout, Menu, Typography } from 'antd'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import { GraphReview } from '@/pages/GraphReview'
import { GraphLibrary } from '@/pages/GraphLibrary'
import { Home } from '@/pages/Home'
import { TeacherWorkspace } from '@/pages/TeacherWorkspace'
import { JobMarketDashboard } from '@/pages/JobMarketDashboard'
import { CurriculumGapDashboard } from '@/pages/CurriculumGapDashboard'
import { CurriculumOptimization } from '@/pages/CurriculumOptimization'
import { TutorPage } from '@/pages/TutorPage'
import { UserTestingPage } from '@/pages/UserTestingPage'
import { AssessmentPage } from '@/pages/AssessmentPage'
import { AdminDashboard } from '@/pages/AdminDashboard'
import { JobDataImportPage } from '@/pages/JobDataImportPage'
import { StudentDashboard } from '@/pages/StudentDashboard'
import { TrainingTaskDetail } from '@/pages/TrainingTaskDetail'
import { TrainingTaskLibrary } from '@/pages/TrainingTaskLibrary'

const { Header, Content, Footer } = Layout
const { Text } = Typography

const NAV_ITEMS = [
  { key: '/', label: <Link to="/">首页</Link> },
  { key: '/teacher', label: <Link to="/teacher">教师端</Link> },
  { key: '/student', label: <Link to="/student">学生端</Link> },
  { key: '/admin', label: <Link to="/admin">管理端</Link> },
]

function App() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const selectedKey = NAV_ITEMS.map((item) => item.key)
    .filter((key) => key !== '/' && pathname.startsWith(key))
    .at(0) ?? '/'

  const managementRoutes = [
    '/teacher/curriculum-gap',
    '/teacher/curriculum-optimization',
    '/teacher/user-testing',
  ]
  const backTarget = pathname.startsWith('/student')
    ? '/student'
    : pathname.startsWith('/admin/')
      ? '/admin'
    : managementRoutes.includes(pathname)
      ? '/admin'
      : pathname.startsWith('/teacher/')
        ? '/teacher'
        : null
  const returnToPrevious = () => {
    if ((window.history.state?.idx ?? 0) > 0) {
      navigate(-1)
      return
    }
    if (backTarget) navigate(backTarget)
  }

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <div className="app-header__inner">
          <Link to="/" className="app-brand" aria-label="SkillTwin AI 首页">
            <span className="app-brand__mark" aria-hidden="true">
              <svg viewBox="0 0 48 48" fill="none">
                <path d="M14 16.5 24 31l10-14.5" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M16.5 16.5h15" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" />
                <circle cx="14" cy="16" r="4.25" fill="#9edcff" />
                <circle cx="34" cy="16" r="4.25" fill="#72c8ff" />
                <circle cx="24" cy="32" r="4.25" fill="#82e2bd" />
                <circle cx="14" cy="16" r="1.25" fill="#0a396b" />
                <circle cx="34" cy="16" r="1.25" fill="#0a396b" />
                <circle cx="24" cy="32" r="1.25" fill="#0a396b" />
              </svg>
            </span>
            <span>
              <strong>SkillTwin AI</strong>
              <small>职业教育岗位能力智能体</small>
            </span>
          </Link>
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[selectedKey]}
            items={NAV_ITEMS}
            className="app-navigation"
          />
          <div className="app-header__context">
            <span className="app-header__scenario">AI 数据标注工程师</span>
            <span className="app-header__status"><i /> 系统已连接</span>
          </div>
        </div>
      </Header>

      <Content className="app-content">
        <main className="app-shell">
          {backTarget && pathname !== '/teacher/market' && pathname !== '/teacher/graphs' && pathname !== '/teacher/tasks' && (
            <div className="portal-backbar">
              <Button type="text" onClick={returnToPrevious}>← 返回上一步</Button>
            </div>
          )}
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/teacher" element={<TeacherWorkspace />} />
            <Route path="/teacher/market" element={<JobMarketDashboard />} />
            <Route path="/teacher/curriculum-gap" element={<CurriculumGapDashboard />} />
            <Route path="/teacher/curriculum-optimization" element={<CurriculumOptimization />} />
            <Route path="/teacher/user-testing" element={<UserTestingPage />} />
            <Route path="/teacher/graphs" element={<GraphLibrary />} />
            <Route path="/teacher/graphs/:graphId" element={<GraphReview />} />
            <Route path="/teacher/tasks" element={<TrainingTaskLibrary />} />
            <Route path="/teacher/tasks/:taskId" element={<TrainingTaskDetail />} />
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/admin/job-data" element={<JobDataImportPage />} />
            <Route path="/student" element={<StudentDashboard />} />
            <Route path="/student/tutor" element={<TutorPage />} />
            <Route
              path="/student/tasks/:taskId"
              element={<TrainingTaskDetail audience="student" />}
            />
            <Route
              path="/student/assessments/:assessmentId"
              element={<AssessmentPage />}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </Content>

      <Footer className="app-footer">
        <Text type="secondary">
          SkillTwin AI · 职业教育岗位能力与个性化实训智能体 · 系统生成内容均标注「AI 生成」并附依据来源
        </Text>
      </Footer>
    </Layout>
  )
}

export default App
