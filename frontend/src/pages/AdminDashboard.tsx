import { Button, Card, Col, Row, Space, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'

import { PageHero } from '@/components/PageHero'

const { Title, Paragraph, Text } = Typography

/** 专业负责人、课程负责人和比赛团队使用的建设与验证工具。 */
export function AdminDashboard() {
  const navigate = useNavigate()
  const tools = [
    {
      title: '岗位数据导入',
      description: '导入保留岗位原文与公开来源的 JD，自动校验、脱敏、去重，并重建岗位技能需求统计。',
      action: '进入数据导入',
      route: '/admin/job-data',
      className: 'admin-tool-card--brown',
    },
    {
      title: '课程对标',
      description: '导入人才培养方案后，核验课程材料与岗位能力图谱的覆盖关系和未映射项。',
      action: '进入课程对标',
      route: '/teacher/curriculum-gap',
      className: 'admin-tool-card--blue',
    },
    {
      title: '培养方案优化',
      description: '结合岗位需求频率与课程覆盖比例，为课程调整提供可回查的优先级建议。',
      action: '查看优化建议',
      route: '/teacher/curriculum-optimization',
      className: 'admin-tool-card--pink',
    },
    {
      title: '真实用户测试',
      description: '邀请教师或学生试用，记录任务结果、易用性与满意度，形成比赛验证证据。',
      action: '记录测试反馈',
      route: '/teacher/user-testing',
      className: 'admin-tool-card--purple',
    },
  ]

  return (
    <Space orientation="vertical" size={24} style={{ width: '100%' }}>
      <PageHero
        eyebrow="管理端 · 课程建设与项目验证"
        title="管理专业建设，验证教学效果"
        description="为专业负责人、课程负责人和比赛团队提供课程优化与真实试用的辅助工具。"
        meta={<Tag color="cyan">不属于教师日常备课三步</Tag>}
      />

      <Card className="admin-tools-panel" title="管理工具" extra={<Text type="secondary">选择需要开展的管理工作</Text>}>
        <Row gutter={[18, 18]}>
          {tools.map((tool, index) => (
            <Col xs={24} md={12} xl={6} key={tool.title}>
              <Card className={`admin-tool-card ${tool.className}`}>
                <span className="admin-tool-card__number">0{index + 1}</span>
                <Title level={3}>{tool.title}</Title>
                <Paragraph>{tool.description}</Paragraph>
                <Button type="default" onClick={() => navigate(tool.route)}>{tool.action} →</Button>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </Space>
  )
}
