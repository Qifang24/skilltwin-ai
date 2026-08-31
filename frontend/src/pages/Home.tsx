/**
 * 首页：教师端 / 学生端入口 + 系统状态。
 *
 * 页面上出现的功能条目都标注了所属 Phase 与是否已实现，
 * 避免出现「看起来能用、点进去是空的」的演示型 UI。
 */

import { Badge, Card, Col, Row, Space, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'

import { SystemStatusCard } from '@/components/SystemStatusCard'

const { Title, Paragraph, Text } = Typography

interface FeatureEntry {
  name: string
  phase: string
  ready: boolean
}

const TEACHER_FEATURES: FeatureEntry[] = [
  { name: '岗位能力图谱生成与审核', phase: 'Phase 5–6', ready: true },
  { name: '实训任务生成与发布', phase: 'Phase 7', ready: true },
  { name: '岗位需求趋势分析', phase: 'Phase 10', ready: true },
  { name: '课程 Gap Analysis', phase: 'Phase 11', ready: true },
  { name: '培养方案优化建议', phase: 'Phase 12', ready: true },
  { name: '真实用户测试与报告', phase: 'Phase 15', ready: true },
]

const STUDENT_FEATURES: FeatureEntry[] = [
  { name: '岗位能力诊断测评', phase: 'Phase 8', ready: true },
  { name: '能力雷达图与置信区间', phase: 'Phase 8', ready: true },
  { name: '能力 Gap 分析', phase: 'Phase 8', ready: true },
  { name: '个性化学习路径', phase: 'Phase 9', ready: true },
  { name: 'AI 学习助手', phase: 'Phase 13', ready: true },
]

function FeatureList({ features }: { features: FeatureEntry[] }) {
  return (
    <Space orientation="vertical" size={8} style={{ width: '100%' }}>
      {features.map((feature) => (
        <Space key={feature.name} size={8}>
          <Badge status={feature.ready ? 'success' : 'default'} />
          <Text type={feature.ready ? undefined : 'secondary'}>{feature.name}</Text>
          <Tag color={feature.ready ? 'green' : 'default'}>
            {feature.ready ? '已上线' : feature.phase}
          </Tag>
        </Space>
      ))}
    </Space>
  )
}

export function Home() {
  return (
    <Space orientation="vertical" size={28} style={{ width: '100%' }}>
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero__copy">
          <div className="landing-hero__eyebrow">
            <span aria-hidden="true">◇</span> Evidence-based AI · 可追溯、可审核
          </div>
          <Title id="landing-title" level={1} className="landing-hero__title">
            让岗位定义学习，<br />
            <span>让能力驱动成长</span>
          </Title>
          <Paragraph className="landing-hero__description">
            面向人工智能技术应用专业群，将真实岗位需求转化为课程、实训与学生的个性化成长路径。
          </Paragraph>
          <Space wrap size={[8, 8]}>
            <Tag color="blue">AI 数据标注工程师</Tag>
            <Tag color="cyan">岗位证据可回查</Tag>
            <Tag color="green">学习闭环可量化</Tag>
          </Space>
        </div>
        <div className="learning-loop" aria-label="SkillTwin AI 学习闭环">
          <div className="learning-loop__item"><span>01</span>产业岗位需求</div>
          <div className="learning-loop__arrow">→</div>
          <div className="learning-loop__item"><span>02</span>岗位能力图谱</div>
          <div className="learning-loop__arrow">→</div>
          <div className="learning-loop__item"><span>03</span>课程与实训</div>
          <div className="learning-loop__arrow">→</div>
          <div className="learning-loop__item learning-loop__item--accent"><span>04</span>学生能力成长</div>
        </div>
      </section>

      <Row gutter={[24, 24]}>
        <Col xs={24} md={12}>
          <Card
            className="portal-card"
            title={<Space><span className="portal-card__symbol" aria-hidden="true">教</span> 教师端</Space>}
            hoverable
            extra={<Link to="/teacher">进入工作台 →</Link>}
          >
            {/* 中文正文写成单行：JSX 会把换行折成空格，多行会在标点后留下空隙 */}
            <Paragraph type="secondary">
              面向专业负责人与任课教师：分析岗位需求变化，审核岗位能力图谱，对照课程找出能力缺口，并生成可直接用于教学的实训任务。
            </Paragraph>
            <FeatureList features={TEACHER_FEATURES} />
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card
            className="portal-card"
            title={<Space><span className="portal-card__symbol" aria-hidden="true">学</span> 学生端</Space>}
            hoverable
            extra={<Link to="/student">进入学习中心 →</Link>}
          >
            <Paragraph type="secondary">
              面向学生：选定目标岗位后完成能力诊断，系统生成个人能力画像，对比岗位要求算出差距，并给出可执行的个性化学习路径。
            </Paragraph>
            <FeatureList features={STUDENT_FEATURES} />
          </Card>
        </Col>
      </Row>

      <SystemStatusCard />
    </Space>
  )
}
