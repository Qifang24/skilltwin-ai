/**
 * 尚未实现的路由占位页。
 *
 * 刻意做成「明确说明未实现」而不是假装有内容 —— 项目原则之一是
 * 不做看起来很厉害但背后没有真实数据的演示型界面。
 */

import { Button, Empty, Result, Space, Typography } from 'antd'
import { Link } from 'react-router-dom'

const { Text } = Typography

interface PlaceholderProps {
  title: string
  phase: string
  description: string
}

export function Placeholder({ title, phase, description }: PlaceholderProps) {
  return (
    <Result
      icon={<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />}
      title={title}
      subTitle={
        <Space direction="vertical" size={4}>
          <Text>{description}</Text>
          <Text type="secondary">当前进度：{phase} 尚未开始</Text>
        </Space>
      }
      extra={
        <Link to="/">
          <Button type="primary">返回首页</Button>
        </Link>
      }
    />
  )
}
