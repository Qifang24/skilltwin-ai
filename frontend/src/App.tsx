import { Layout, Menu, Typography } from 'antd'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { GraphReview } from '@/pages/GraphReview'
import { Home } from '@/pages/Home'
import { TeacherWorkspace } from '@/pages/TeacherWorkspace'
import { JobMarketDashboard } from '@/pages/JobMarketDashboard'
import { CurriculumGapDashboard } from '@/pages/CurriculumGapDashboard'
import { CurriculumOptimization } from '@/pages/CurriculumOptimization'
import { TutorPage } from '@/pages/TutorPage'
import { UserTestingPage } from '@/pages/UserTestingPage'
import { AssessmentPage } from '@/pages/AssessmentPage'
import { StudentDashboard } from '@/pages/StudentDashboard'
import { TrainingTaskDetail } from '@/pages/TrainingTaskDetail'

const { Header, Content, Footer } = Layout
const { Text } = Typography

const NAV_ITEMS = [
  { key: '/', label: <Link to="/">首页</Link> },
  { key: '/teacher', label: <Link to="/teacher">教师端</Link> },
  { key: '/student', label: <Link to="/student">学生端</Link> },
]

function App() {
  const { pathname } = useLocation()
  const selectedKey = NAV_ITEMS.map((item) => item.key)
    .filter((key) => key !== '/' && pathname.startsWith(key))
    .at(0) ?? '/'

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <Link to="/" className="app-brand" aria-label="SkillTwin AI 首页">
          <span className="app-brand__mark" aria-hidden="true">ST</span>
          <span>
            <strong>SkillTwin AI</strong>
            <small>岗位能力智能体</small>
          </span>
        </Link>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey]}
          items={NAV_ITEMS}
          className="app-navigation"
        />
      </Header>

      <Content className="app-content">
        <main className="app-shell">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/teacher" element={<TeacherWorkspace />} />
            <Route path="/teacher/market" element={<JobMarketDashboard />} />
            <Route path="/teacher/curriculum-gap" element={<CurriculumGapDashboard />} />
            <Route path="/teacher/curriculum-optimization" element={<CurriculumOptimization />} />
            <Route path="/teacher/user-testing" element={<UserTestingPage />} />
            <Route path="/teacher/graphs/:graphId" element={<GraphReview />} />
            <Route path="/teacher/tasks/:taskId" element={<TrainingTaskDetail />} />
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
