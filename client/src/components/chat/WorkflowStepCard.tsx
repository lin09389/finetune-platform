import { memo } from 'react';
import { Tag, Tooltip } from 'antd';
import { motion } from 'framer-motion';

type WorkflowStepLike = {
  id: string;
  step_key?: string;
  title?: string;
  description?: string;
  status?: string;
  agent_id?: string;
  legacy_role?: string;
  requires_approval?: boolean;
  input_data?: Record<string, any>;
  output_data?: Record<string, any>;
  output?: Record<string, any>;
  error?: string;
};

type StepToolEvent = {
  id: string;
  toolName: string;
  status: string;
  summary?: string;
  durationMs?: number;
  error?: string;
};

interface WorkflowStepCardProps {
  index: number;
  step: WorkflowStepLike;
  active?: boolean;
  toolEvents?: StepToolEvent[];
}

const statusMap: Record<string, { color: string; label: string }> = {
  running: { color: 'processing', label: '进行中' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
  blocked: { color: 'warning', label: '阻塞' },
  waiting_approval: { color: 'gold', label: '待审批' },
  pending: { color: 'default', label: '待处理' },
};

const WorkflowStepCard = memo(function WorkflowStepCard({ index, step, active, toolEvents = [] }: WorkflowStepCardProps) {
  const statusKey = (step.status || 'pending').toLowerCase();
  const status = statusMap[statusKey] ?? { color: 'default', label: '待处理' };
  const summary = step.output?.summary || step.output_data?.summary || step.description || '暂无摘要';
  const reason = step.output?.reason || step.output_data?.reason || step.error || step.input_data?.reason || '';
  const fix = step.output?.fix || step.output_data?.fix || step.output?.next_action || step.output_data?.next_action || '';
  const problem = step.output?.problem || step.output_data?.problem || step.input_data?.problem || summary;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.2 }}
      style={{
        borderRadius: 16,
        border: active
          ? '1px solid color-mix(in srgb, var(--accent-primary) 40%, transparent)'
          : '1px solid color-mix(in srgb, var(--border-color) 64%, transparent)',
        background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 98%, transparent), color-mix(in srgb, var(--bg-secondary) 94%, transparent))',
        boxShadow: active ? '0 10px 28px rgba(0,0,0,0.14)' : '0 5px 16px rgba(0,0,0,0.06)',
        padding: 18,
        marginBottom: 10,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', flexWrap: 'wrap' }}>
          <div style={{
            width: 34,
            height: 34,
            borderRadius: 12,
            display: 'grid',
            placeItems: 'center',
            background: 'color-mix(in srgb, var(--accent-primary) 14%, transparent)',
            color: 'var(--accent-primary)',
            fontWeight: 700,
          }}>
            {index}
          </div>
          <div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
                {step.title || step.step_key || `Stage ${index}`}
              </h3>
              <Tag color={status.color as any} style={{ marginInlineEnd: 0, borderRadius: 999 }}>
                {status.label}
              </Tag>
              {step.requires_approval ? <Tag color="gold" style={{ marginInlineEnd: 0, borderRadius: 999 }}>需审批</Tag> : null}
            </div>
            <div style={{ marginTop: 4, color: 'var(--text-secondary)', fontSize: 13 }}>
              {step.agent_id ? `Agent: ${step.agent_id}` : ''}
              {step.legacy_role ? ` · ${step.legacy_role}` : ''}
            </div>
          </div>
        </div>
        <Tooltip title={step.step_key || step.id}>
          <span style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>Node #{step.step_key || step.id}</span>
        </Tooltip>
      </div>

      <div style={{ marginTop: 14, display: 'grid', gap: 10 }}>
        <section style={{ padding: 12, borderRadius: 14, background: 'color-mix(in srgb, var(--bg-secondary) 78%, transparent)' }}>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 4 }}>Stage 目标</div>
          <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text-primary)' }}>{problem}</div>
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 12, alignItems: 'stretch' }}>
          {reason ? (
            <section style={{
              minHeight: 110,
              padding: 12,
              borderRadius: 14,
              background: 'color-mix(in srgb, var(--bg-secondary) 72%, transparent)',
              border: '1px solid color-mix(in srgb, var(--border-color) 48%, transparent)',
              display: 'flex',
              flexDirection: 'column',
            }}>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 6, letterSpacing: '0.06em' }}>Node 原因</div>
              <div style={{ fontSize: 14, lineHeight: 1.75, color: 'var(--text-primary)', flex: 1 }}>{reason}</div>
            </section>
          ) : <div />}
          {fix ? (
            <section style={{
              minHeight: 110,
              padding: 12,
              borderRadius: 14,
              background: 'color-mix(in srgb, var(--bg-secondary) 72%, transparent)',
              border: '1px solid color-mix(in srgb, var(--border-color) 48%, transparent)',
              display: 'flex',
              flexDirection: 'column',
            }}>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 6, letterSpacing: '0.06em' }}>Node 修复</div>
              <div style={{ fontSize: 14, lineHeight: 1.75, color: 'var(--text-primary)', flex: 1 }}>{fix}</div>
            </section>
          ) : <div />}
        </div>

        {toolEvents.length > 0 ? (
          <section style={{
            padding: 12,
            borderRadius: 14,
            background: 'color-mix(in srgb, var(--bg-secondary) 72%, transparent)',
            border: '1px solid color-mix(in srgb, var(--border-color) 48%, transparent)',
          }}>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 8, letterSpacing: '0.06em' }}>Node 关联工具</div>
            <div style={{ display: 'grid', gap: 8 }}>
              {toolEvents.map((tool) => (
                <div key={tool.id} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 12,
                  alignItems: 'flex-start',
                  padding: '10px 12px',
                  borderRadius: 12,
                  background: 'color-mix(in srgb, var(--bg-elevated) 88%, transparent)',
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{tool.toolName}</div>
                    {tool.summary ? <div style={{ marginTop: 4, fontSize: 13, lineHeight: 1.65, color: 'var(--text-secondary)' }}>{tool.summary}</div> : null}
                    {tool.error ? <div style={{ marginTop: 4, fontSize: 13, lineHeight: 1.65, color: 'var(--error-color, #ff4d4f)' }}>{tool.error}</div> : null}
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <Tag color={tool.status === 'completed' ? 'success' : tool.status === 'failed' ? 'error' : tool.status === 'blocked' ? 'warning' : 'processing'} style={{ marginInlineEnd: 0, borderRadius: 999 }}>
                      {tool.status}
                    </Tag>
                    {typeof tool.durationMs === 'number' ? <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-tertiary)' }}>{tool.durationMs} ms</div> : null}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </motion.div>
  );
});

export default WorkflowStepCard;
