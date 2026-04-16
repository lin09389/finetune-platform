import React, { memo } from 'react'
import { Alert } from 'antd'
import GlassCard from './GlassCard'
import StatusBadge, { type StatusType } from './StatusBadge'

interface InsightMetric {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode
}

interface InsightSection {
  title: string
  items: string[]
  tone?: 'default' | 'warning'
}

export interface InsightPanelProps {
  title: string
  status?: {
    type: StatusType
    text: string
  }
  summary?: React.ReactNode
  metrics?: InsightMetric[]
  sections?: InsightSection[]
  footer?: React.ReactNode
  actions?: React.ReactNode
  embedded?: boolean
  testId?: string
}

const panelStyles = {
  shell: {
    display: 'grid',
    gap: 16,
  } as React.CSSProperties,
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  } as React.CSSProperties,
  title: {
    margin: 0,
    fontSize: 18,
    color: 'var(--text-primary)',
  } as React.CSSProperties,
  summary: {
    margin: 0,
    fontSize: 13,
    lineHeight: 1.6,
    color: 'var(--text-secondary)',
  } as React.CSSProperties,
  metrics: {
    display: 'grid',
    gap: 12,
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
  } as React.CSSProperties,
  metricCard: {
    padding: 12,
    borderRadius: 10,
    border: '1px solid var(--border-color)',
    background: 'var(--bg-elevated)',
  } as React.CSSProperties,
  metricLabel: {
    fontSize: 12,
    color: 'var(--text-secondary)',
    marginBottom: 6,
  } as React.CSSProperties,
  metricValue: {
    fontSize: 20,
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  } as React.CSSProperties,
  metricHint: {
    marginTop: 6,
    fontSize: 12,
    color: 'var(--text-secondary)',
  } as React.CSSProperties,
  sectionTitle: {
    margin: '0 0 8px',
    fontSize: 13,
    fontWeight: 600,
    color: 'var(--text-primary)',
  } as React.CSSProperties,
  list: {
    margin: 0,
    paddingLeft: 18,
    color: 'var(--text-secondary)',
    fontSize: 13,
    lineHeight: 1.6,
  } as React.CSSProperties,
  footer: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    lineHeight: 1.6,
  } as React.CSSProperties,
}

const InsightPanel: React.FC<InsightPanelProps> = memo(
  ({ title, status, summary, metrics = [], sections = [], footer, actions, embedded = false, testId }) => {
    const content = (
      <div style={panelStyles.shell} data-testid={testId}>
        <div style={panelStyles.header}>
          <div style={{ display: 'grid', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <h3 style={panelStyles.title}>{title}</h3>
              {status && <StatusBadge status={status.type} text={status.text} />}
            </div>
            {summary && <div style={panelStyles.summary}>{summary}</div>}
          </div>
          {actions}
        </div>

        {metrics.length > 0 && (
          <div style={panelStyles.metrics}>
            {metrics.map((metric) => (
              <div key={metric.label} style={panelStyles.metricCard}>
                <div style={panelStyles.metricLabel}>{metric.label}</div>
                <div style={panelStyles.metricValue}>{metric.value}</div>
                {metric.hint && <div style={panelStyles.metricHint}>{metric.hint}</div>}
              </div>
            ))}
          </div>
        )}

        {sections.map((section) => (
          section.items.length > 0 ? (
            <div key={section.title}>
              <div style={panelStyles.sectionTitle}>{section.title}</div>
              {section.tone === 'warning' ? (
                <Alert
                  type="warning"
                  showIcon
                  message={
                    <ul style={panelStyles.list}>
                      {section.items.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  }
                />
              ) : (
                <ul style={panelStyles.list}>
                  {section.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
            </div>
          ) : null
        ))}

        {footer && <div style={panelStyles.footer}>{footer}</div>}
      </div>
    )

    if (embedded) {
      return content
    }

    return (
      <GlassCard intensity="medium" noHover>
        {content}
      </GlassCard>
    )
  }
)

InsightPanel.displayName = 'InsightPanel'

export default InsightPanel
