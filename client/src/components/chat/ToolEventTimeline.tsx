import { memo } from 'react';
import ToolEventCard from './ToolEventCard';

type ToolTimelineEvent = {
  id: string;
  toolName: string;
  status: string;
  summary?: string;
  agentId?: string;
  durationMs?: number;
  error?: string;
  stepId?: string;
};

interface ToolEventTimelineProps {
  events: ToolTimelineEvent[];
}

const ToolEventTimeline = memo(function ToolEventTimeline({ events }: ToolEventTimelineProps) {
  if (!events.length) return null;

  return (
    <section
      style={{
        marginBottom: 18,
        padding: '14px 16px 4px',
        borderRadius: 18,
        border: '1px solid color-mix(in srgb, var(--border-color) 62%, transparent)',
        background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 96%, transparent), color-mix(in srgb, var(--bg-secondary) 92%, transparent))',
      }}
    >
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Tool Timeline
          </div>
          <div style={{ marginTop: 2, fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>
            工具调用时间线
          </div>
        </div>
        <div style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>{events.length} events</div>
      </div>

      <div style={{ position: 'relative', paddingLeft: 18 }}>
        <div
          aria-hidden
          style={{
            position: 'absolute',
            left: 5,
            top: 4,
            bottom: 12,
            width: 2,
            borderRadius: 999,
            background: 'color-mix(in srgb, var(--accent-primary) 22%, var(--border-color))',
          }}
        />
        {events.map((event, index) => (
          <div key={event.id} style={{ position: 'relative' }}>
            <div
              aria-hidden
              style={{
                position: 'absolute',
                left: -17,
                top: 18,
                width: 10,
                height: 10,
                borderRadius: 999,
                background: event.status === 'running'
                  ? 'var(--accent-primary)'
                  : event.status === 'failed'
                    ? 'var(--error-color, #ff4d4f)'
                    : 'color-mix(in srgb, var(--accent-primary) 36%, var(--bg-elevated))',
                boxShadow: event.status === 'running' ? '0 0 0 6px color-mix(in srgb, var(--accent-primary) 12%, transparent)' : 'none',
              }}
            />
            <ToolEventCard
              toolName={event.toolName}
              status={event.status}
              summary={event.summary}
              agentId={event.agentId}
              durationMs={event.durationMs}
              error={event.error}
              active={index === events.length - 1 && event.status === 'running'}
            />
          </div>
        ))}
      </div>
    </section>
  );
});

export default ToolEventTimeline;
