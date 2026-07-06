import { Alert } from 'antd';
import React, { memo } from 'react';
import GlassCard from './GlassCard';
import StatusBadge, { type StatusType } from './StatusBadge';

interface InsightMetric {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
}

interface InsightSection {
  title: string;
  items: string[];
  tone?: 'default' | 'warning';
}

export interface InsightPanelProps {
  title: string;
  status?: {
    type: StatusType;
    text: string;
  };
  summary?: React.ReactNode;
  metrics?: InsightMetric[];
  sections?: InsightSection[];
  footer?: React.ReactNode;
  actions?: React.ReactNode;
  embedded?: boolean;
  testId?: string;
}

const panelStyles = {
  shell: {
    display: 'grid',
    gap: 'var(--space-4)',
  } as React.CSSProperties,
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 'var(--space-3)',
  } as React.CSSProperties,
  title: {
    margin: 0,
    fontSize: 'var(--text-lg)',
    fontFamily: 'var(--font-display)',
    fontWeight: 'var(--font-semibold)',
    color: 'var(--text-primary)',
  } as React.CSSProperties,
  summary: {
    margin: 0,
    fontSize: 'var(--text-sm)',
    lineHeight: 'var(--leading-relaxed)',
    fontFamily: 'var(--font-reading)',
    color: 'var(--text-secondary)',
  } as React.CSSProperties,
  metrics: {
    display: 'grid',
    gap: 'var(--space-3)',
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
  } as React.CSSProperties,
  metricCard: {
    padding: 'var(--space-3)',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-color)',
    background: 'var(--bg-elevated)',
  } as React.CSSProperties,
  metricLabel: {
    fontSize: 'var(--text-xs)',
    fontFamily: 'var(--font-sans)',
    color: 'var(--text-secondary)',
    marginBottom: 'var(--space-1-5)',
  } as React.CSSProperties,
  metricValue: {
    fontSize: 'var(--text-xl)',
    fontWeight: 'var(--font-bold)',
    fontFamily: 'var(--font-display)',
    color: 'var(--text-primary)',
    lineHeight: 'var(--leading-tight)',
  } as React.CSSProperties,
  metricHint: {
    marginTop: 'var(--space-1-5)',
    fontSize: 'var(--text-xs)',
    color: 'var(--text-secondary)',
  } as React.CSSProperties,
  sectionTitle: {
    margin: '0 0 var(--space-2)',
    fontSize: 'var(--text-sm)',
    fontWeight: 'var(--font-semibold)',
    fontFamily: 'var(--font-sans)',
    color: 'var(--text-primary)',
  } as React.CSSProperties,
  list: {
    margin: 0,
    paddingLeft: 'var(--space-5)',
    color: 'var(--text-secondary)',
    fontSize: 'var(--text-sm)',
    lineHeight: 'var(--leading-relaxed)',
    fontFamily: 'var(--font-reading)',
  } as React.CSSProperties,
  footer: {
    fontSize: 'var(--text-sm)',
    color: 'var(--text-secondary)',
    lineHeight: 'var(--leading-relaxed)',
    fontFamily: 'var(--font-reading)',
  } as React.CSSProperties,
};

const InsightPanel: React.FC<InsightPanelProps> = memo(
  ({
    title,
    status,
    summary,
    metrics = [],
    sections = [],
    footer,
    actions,
    embedded = false,
    testId,
  }) => {
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

        {sections.map((section) =>
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
          ) : null,
        )}

        {footer && <div style={panelStyles.footer}>{footer}</div>}
      </div>
    );

    if (embedded) {
      return content;
    }

    return (
      <GlassCard intensity="medium" noHover>
        {content}
      </GlassCard>
    );
  },
);

InsightPanel.displayName = 'InsightPanel';

export default InsightPanel;
