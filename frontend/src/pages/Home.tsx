/**
 * 首页：教师端 / 学生端入口 + 系统状态。
 *
 * 页面上出现的功能条目都标注了所属 Phase 与是否已实现，
 * 避免出现「看起来能用、点进去是空的」的演示型 UI。
 */

import { Button, Card, Col, Row, Space, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'

import { SystemStatusCard } from '@/components/SystemStatusCard'

const { Title, Paragraph } = Typography

export function Home() {
  return (
    <Space orientation="vertical" size={28} style={{ width: '100%' }}>
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero__copy">
          <div className="landing-hero__eyebrow">
            <span aria-hidden="true">✦</span> 可追溯 · 可审核 · 可持续优化
          </div>
          <Title id="landing-title" level={1} className="landing-hero__title">
            以岗位需求定教学，<br />
            <span>以能力差距促成长</span>
          </Title>
          <Paragraph className="landing-hero__description">
            面向人工智能技术应用专业群，以真实岗位需求驱动课程、实训与个性化成长。
          </Paragraph>
          <Space wrap size={[8, 8]}>
            <Tag color="blue">AI 数据标注工程师</Tag>
            <Tag color="cyan">岗位证据可回查</Tag>
            <Tag color="green">学习闭环可量化</Tag>
          </Space>
          <div className="landing-hero__actions">
            <Link to="/teacher"><Button type="primary" size="large">我是教师，开始备课</Button></Link>
            <Link to="/student"><Button size="large">我是学生，开始学习</Button></Link>
          </div>
          <p className="landing-hero__proof">
            <span aria-hidden="true">✓</span> 以岗位原文、职业标准和教师审核作为每一项建议的依据
          </p>
        </div>
        <div className="learning-loop" aria-label="SkillTwin AI 教学能力闭环">
          <div className="learning-loop__heading">
            <span>SKILLTWIN LOOP</span>
            <strong>岗位驱动的教学闭环</strong>
          </div>
          <div className="learning-loop__grid">
            <div className="learning-loop__item"><span>01</span><strong>岗位洞察</strong><small>真实 JD 与技能需求</small></div>
            <div className="learning-loop__item"><span>02</span><strong>能力建模</strong><small>图谱生成与教师审核</small></div>
            <div className="learning-loop__item"><span>03</span><strong>实训设计</strong><small>学习型任务与评价</small></div>
            <div className="learning-loop__item learning-loop__item--accent"><span>04</span><strong>成长反馈</strong><small>诊断、路径与复测</small></div>
          </div>
        </div>
      </section>

      <Row gutter={[24, 24]}>
        <Col xs={24} md={12}>
          <Card
            className="portal-card portal-card--teacher"
            hoverable
          >
            <div className="portal-card__role">
              <span className="portal-card__emoji" aria-hidden="true">📚</span>
              <Title level={2}>教师端</Title>
              <Paragraph className="portal-card__description">
                从岗位需求出发，审核能力要求，生成并发布实训任务。
              </Paragraph>
              <div className="portal-steps">
                <span>了解岗位</span><span>审核图谱</span><span>发布实训</span>
              </div>
              <Link to="/teacher"><Button type="primary" size="large">进入教师工作台 →</Button></Link>
            </div>
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card
            className="portal-card portal-card--student"
            hoverable
          >
            <div className="portal-card__role">
              <span className="portal-card__emoji" aria-hidden="true">🎓</span>
              <Title level={2}>学生端</Title>
              <Paragraph className="portal-card__description">
                完成能力诊断，查看能力差距，按个人学习路径练习与复测。
              </Paragraph>
              <div className="portal-steps">
                <span>能力诊断</span><span>查看差距</span><span>按路径学习</span>
              </div>
              <Link to="/student"><Button type="primary" size="large">进入学习中心 →</Button></Link>
            </div>
          </Card>
        </Col>
      </Row>

      <SystemStatusCard />
    </Space>
  )
}
