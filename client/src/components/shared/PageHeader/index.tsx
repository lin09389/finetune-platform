import React, { memo } from 'react'
import { motion } from 'framer-motion'

export interface PageHeaderProps {
  title: string
  subtitle?: string
  icon?: React.ReactNode
  iconBgColor?: string
  actions?: React.ReactNode
  breadcrumbs?: Array<{
    title: string
    href?: string
  }>
  className?: string
  style?: React.CSSProperties
}

const PageHeader: React.FC<PageHeaderProps> = memo(
  ({
    title,
    subtitle,
    icon,
    iconBgColor = 'var(--text-primary)',
    actions,
    breadcrumbs,
    className,
    style,
  }) => {
    return (
      <motion.div
        className={className}
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        style={{
          marginBottom: 24,
          ...style,
        }}
      >
        {breadcrumbs && breadcrumbs.length > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 12,
              fontSize: 'var(--text-sm)',
            }}
          >
            {breadcrumbs.map((item, index) => (
              <React.Fragment key={index}>
                {item.href ? (
                  <a
                    href={item.href}
                    style={{
                      color: 'var(--text-secondary)',
                      textDecoration: 'none',
                      transition: 'color 0.2s',
                    }}
                  >
                    {item.title}
                  </a>
                ) : (
                  <span style={{ color: 'var(--text-primary)' }}>{item.title}</span>
                )}
                {index < breadcrumbs.length - 1 && (
                  <span style={{ color: 'var(--text-tertiary)' }}>/</span>
                )}
              </React.Fragment>
            ))}
          </div>
        )}

        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            {icon && (
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 'var(--radius-md)',
                  background: iconBgColor,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 18,
                  color: '#fff',
                  flexShrink: 0,
                }}
              >
                {icon}
              </div>
            )}
            <div>
              <h1
                style={{
                  fontSize: 'var(--text-2xl)',
                  fontWeight: 600,
                  margin: 0,
                  color: 'var(--text-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                {!icon && (
                  <span
                    style={{
                      display: 'inline-block',
                      width: 4,
                      height: 24,
                      background: 'var(--accent-primary)',
                      borderRadius: 'var(--radius-full)',
                    }}
                  />
                )}
                {title}
              </h1>
              {subtitle && (
                <p
                  style={{
                    margin: '8px 0 0',
                    color: 'var(--text-secondary)',
                    fontSize: 'var(--text-sm)',
                  }}
                >
                  {subtitle}
                </p>
              )}
            </div>
          </div>

          {actions && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                flexShrink: 0,
              }}
            >
              {actions}
            </div>
          )}
        </div>
      </motion.div>
    )
  }
)

PageHeader.displayName = 'PageHeader'

export default PageHeader

export const PageTitle: React.FC<{
  title: string
  subtitle?: string
}> = memo(({ title, subtitle }) => (
  <PageHeader title={title} subtitle={subtitle} />
))

PageTitle.displayName = 'PageTitle'

export const SectionHeader: React.FC<{
  title: string
  icon?: React.ReactNode
  action?: React.ReactNode
}> = memo(({ title, icon, action }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 16,
    }}
  >
    <h3
      style={{
        fontSize: 'var(--text-base)',
        fontWeight: 600,
        margin: 0,
        color: 'var(--text-primary)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}
    >
      {icon && (
        <span style={{ color: 'var(--accent-primary)' }}>{icon}</span>
      )}
      {title}
    </h3>
    {action}
  </div>
))

SectionHeader.displayName = 'SectionHeader'
