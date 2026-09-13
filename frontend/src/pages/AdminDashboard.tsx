import {
  ArrowRightOutlined,
  BarChartOutlined,
  BookOutlined,
  BulbOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  UsergroupAddOutlined,
} from '@ant-design/icons'
import { Button, Card, Col, Row, Space, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'

import { PageHero } from '@/components/PageHero'

const { Title, Paragraph, Text } = Typography

/** 专业负责人、课程负责人和比赛团队使用的建设与验证工具。 */
export function AdminDashboard() {
  const navigate = useNavigate()
  const tools = [
    {
      title: '岗位数据导入',
      kicker: '数据治理',
      helper: 'CSV / JSON · 可追溯导入',
      icon: <DatabaseOutlined />,
      description: '导入保留岗位原文与公开来源的 JD，自动校验、脱敏、去重，并重建岗位技能需求统计。',
      action: '进入数据导入',
      route: '/admin/job-data',
      className: 'admin-tool-card--brown',
    },
    {
      title: '课程对标',
      kicker: '覆盖分析',
      helper: '课程 ↔ 技能图谱',
      icon: <BookOutlined />,
      description: '导入人才培养方案后，核验课程材料与岗位能力图谱的覆盖关系和未映射项。',
      action: '进入课程对标',
      route: '/admin/curriculum-gap',
      className: 'admin-tool-card--blue',
    },
    {
      title: '培养方案优化',
      kicker: '决策建议',
      helper: '缺口优先级 · 证据链',
      icon: <BulbOutlined />,
      description: '结合岗位需求频率与课程覆盖比例，为课程调整提供可回查的优先级建议。',
      action: '查看优化建议',
      route: '/admin/curriculum-optimization',
      className: 'admin-tool-card--pink',
    },
    {
      title: '真实用户测试',
      kicker: '效果验证',
      helper: '任务记录 · 体验反馈',
      icon: <UsergroupAddOutlined />,
      description: '邀请教师或学生试用，记录任务结果、易用性与满意度，形成比赛验证证据。',
      action: '记录测试反馈',
      route: '/admin/user-testing',
      className: 'admin-tool-card--purple',
    },
  ] as Array<{
    title: string
    kicker: string
    helper: string
    icon: ReactNode
    description: string
    action: string
    route: string
    className: string
  }>

  return (
    <Space className="admin-workspace" orientation="vertical" size={24} style={{ width: '100%' }}>
      <PageHero
        eyebrow={'\u7ba1\u7406\u7aef'}
        title={'\u4e13\u4e1a\u5efa\u8bbe\u7ba1\u7406'}
        description={'\u7ba1\u7406\u5c97\u4f4d\u6570\u636e\u3001\u8bfe\u7a0b\u5bf9\u6807\u4e0e\u57f9\u517b\u65b9\u6848\u4f18\u5316\u3002'}
        meta={<div className="admin-hero-meta"><span><FileSearchOutlined /> 数据可追溯</span><span><BarChartOutlined /> 分析结果可回查</span></div>}
      />

      <section className="admin-flow-card" aria-label="专业建设工作流">
        <div className="admin-flow-card__copy">
          <Tag color="blue">闭环工作流</Tag>
          <Title level={4}>从真实岗位到培养方案优化</Title>
          <Typography.Paragraph>
            三个环节共享同一套岗位、能力图谱和课程数据，分析结果可以沿证据链逐层回看。
          </Typography.Paragraph>
        </div>
        <div className="admin-flow-card__track">
          {[
            ['01', '岗位数据', '导入与治理'],
            ['02', '课程对标', '识别覆盖缺口'],
            ['03', '方案优化', '形成可执行建议'],
          ].map(([step, title, detail], index) => (
            <div className="admin-flow-card__step" key={step}>
              <span className="admin-flow-card__step-number">{step}</span>
              <span className="admin-flow-card__step-copy"><strong>{title}</strong><small>{detail}</small></span>
              {index < 2 ? <ArrowRightOutlined className="admin-flow-card__arrow" /> : null}
            </div>
          ))}
        </div>
      </section>

      <Card className="admin-tools-panel" title={<span className="admin-panel-title"><span>管理工具</span><Tag>4 个工作台</Tag></span>} extra={<Text type="secondary">选择需要开展的管理工作</Text>}>
        <Row gutter={[18, 18]}>
          {tools.map((tool, index) => (
            <Col xs={24} md={12} xl={6} key={tool.title}>
              <Card className={`admin-tool-card ${tool.className}`} hoverable>
                <div className="admin-tool-card__top">
                  <span className="admin-tool-card__icon" aria-hidden="true">{tool.icon}</span>
                  <span className="admin-tool-card__kicker">{tool.kicker}</span>
                  <span className="admin-tool-card__number">0{index + 1}</span>
                </div>
                <Title level={3}>{tool.title}</Title>
                <Paragraph>{tool.description}</Paragraph>
                <div className="admin-tool-card__foot">
                  <Button type="default" onClick={() => navigate(tool.route)} icon={<ArrowRightOutlined />} iconPosition="end">{tool.action}</Button>
                  <span>{tool.helper}</span>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </Space>
  )
}
