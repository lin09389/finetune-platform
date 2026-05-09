import { memo } from 'react';
import { Tag } from 'antd';
import { motion } from 'framer-motion';

interface ToolEventCardProps {
  toolName: string;
  status?: string;
  summary?: string;
  agentId?: string;
  durationMs?: number;
  error?: string;
  active?: boolean;
}

const statusMap: Record<string, { color: string; label: string }> = {
  running: { color: 'processing', label: '执行中' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
  blocked: { color: 'warning', label: '阻塞' },
  pending: { color: 'default', label: '待执行' },
};

const ToolEventCard = memo(function ToolEventCard({
  toolName,
  status = 'pending',
  summary,
  agentId,
  durationMs,
  error,
  active,
}: ToolEventCardProps) {
  const safeStatus = statusMap[status] ?? { color: 'default', label: '待执行' };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      style={{
        marginBottom: 10,
        padding: '14px 16px',
        borderRadius: 14,
        border: active
          ? '1px solid color-mix(in srgb, var(--accent-primary) 38%, transparent)'
          : '1px solid color-mix(in srgb, var(--border-color) 58%, transparent)',
        background: active
          ? 'linear-gradient(180deg, color-mix(in srgb, var(--accent-primary) 10%, var(--bg-elevated)), var(--bg-secondary))'
          : 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 96%, transparent), color-mix(in srgb, var(--bg-secondary) 94%, transparent))',
        boxShadow: active ? '0 10px 24px rgba(0,0,0,0.12)' : '0 6px 16px rgba(0,0,0,0.06)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{toolName}</span>
            <Tag color={safeStatus.color as any} style={{ borderRadius: 999, marginInlineEnd: 0 }}>
              {safeStatus.label}
            </Tag>
            {agentId ? (
              <Tag color="geekblue" style={{ borderRadius: 999, marginInlineEnd: 0 }}>
                {agentId}
              </Tag>
            ) : null}
          </div>
          {summary ? (
            <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
              {summary}
            </div>
          ) : null}
          {error ? (
            <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.7, color: 'var(--error-color, #ff4d4f)' }}>
              {error}
            </div>
          ) : null}
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0, color: 'var(--text-tertiary)', fontSize: 12 }}>
          {typeof durationMs === 'number' ? <div>{durationMs} ms</div> : null}
        </div>
      </div>
    </motion.div>
  );
});

export default ToolEventCard;
