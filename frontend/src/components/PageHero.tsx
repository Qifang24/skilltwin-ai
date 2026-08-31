import { Tag, Typography } from 'antd'
import type { ReactNode } from 'react'

const { Paragraph, Title } = Typography

interface PageHeroProps {
  eyebrow: string
  title: string
  description: string
  meta?: ReactNode
  actions?: ReactNode
}

/** Shared contextual header for the teacher and student workspaces. */
export function PageHero({
  eyebrow,
  title,
  description,
  meta,
  actions,
}: PageHeroProps) {
  return (
    <section className="page-hero" aria-labelledby="page-hero-title">
      <div className="page-hero__content">
        <Tag className="page-hero__eyebrow">{eyebrow}</Tag>
        <Title id="page-hero-title" level={2} className="page-hero__title">
          {title}
        </Title>
        <Paragraph className="page-hero__description">{description}</Paragraph>
        {meta ? <div className="page-hero__meta">{meta}</div> : null}
      </div>
      {actions ? <div className="page-hero__actions">{actions}</div> : null}
    </section>
  )
}
