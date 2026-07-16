import {
  BookOutlined,
  DatabaseOutlined,
  HistoryOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Tooltip } from 'antd';
import { useMemo, useState } from 'react';
import {
  selectContextObservability,
  type ContextObservability,
} from '../selectors/contextObservability';
import styles from './AgentContextStatus.module.css';

export interface AgentContextStatusProps {
  metadata?: Record<string, unknown> | null;
  observability?: ContextObservability | null;
  className?: string;
}

function chipClass(tone: ContextObservability['knowledge']['tone']): string {
  if (tone === 'ok') return `${styles.chip} ${styles.chipOk}`;
  if (tone === 'warn') return `${styles.chip} ${styles.chipWarn}`;
  if (tone === 'muted') return `${styles.chip} ${styles.chipMuted}`;
  return `${styles.chip} ${styles.chipNeutral}`;
}

function basename(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] || path;
}

export default function AgentContextStatus({
  metadata,
  observability: observabilityProp,
  className,
}: AgentContextStatusProps) {
  const obs = useMemo(
    () => observabilityProp ?? selectContextObservability(metadata || null),
    [metadata, observabilityProp],
  );
  const [open, setOpen] = useState(false);

  if (!obs.hasSignal) {
    return (
      <div className={`${styles.card} ${className || ''}`.trim()} aria-label="上下文状态">
        <p className={styles.empty}>任务运行后将显示知识库、外置与上下文刷新状态</p>
      </div>
    );
  }

  const canExpand =
    obs.refresh.hasSignal
    || obs.warnings.length > 0
    || Boolean(obs.knowledge.collectionId)
    || Boolean(obs.projectRetrievalStatus);

  const sessionBits = [
    obs.refresh.changedCount > 0 ? `写入 ${obs.refresh.changedCount}` : '',
    obs.refresh.failureCount > 0 ? `失败 ${obs.refresh.failureCount}` : '',
    obs.refresh.toolOffloadCount > 0 ? `外置 ${obs.refresh.toolOffloadCount}` : '',
    obs.refresh.toolTruncateCount > 0 && obs.refresh.toolOffloadCount === 0
      ? `截断 ${obs.refresh.toolTruncateCount}`
      : '',
  ].filter(Boolean);

  return (
    <div className={`${styles.card} ${className || ''}`.trim()} aria-label="上下文状态">
      <div className={styles.row}>
        <BookOutlined aria-hidden />
        <span>知识库</span>
        <Tooltip title={obs.knowledge.detail}>
          <span className={chipClass(obs.knowledge.tone)}>{obs.knowledge.label}</span>
        </Tooltip>
      </div>

      <div className={styles.row}>
        <DatabaseOutlined aria-hidden />
        <span>项目检索</span>
        <strong>
          {obs.projectRetrievalStatus
            ? String(obs.projectRetrievalStatus)
            : obs.virtualFileCount != null
              ? `${obs.virtualFileCount} 个虚拟文件`
              : '—'}
        </strong>
      </div>

      {obs.refresh.hasSignal ? (
        <div className={styles.row}>
          <HistoryOutlined aria-hidden />
          <span>本会话上下文</span>
          <strong>{sessionBits.join(' · ') || '—'}</strong>
        </div>
      ) : null}

      {obs.warnings.some((w) => /knowledge|retrieval|budget|redact|offload/i.test(w)) ? (
        <div className={styles.row}>
          <WarningOutlined aria-hidden />
          <span>提示</span>
          <strong>{obs.warnings.length} 条</strong>
        </div>
      ) : null}

      {canExpand ? (
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? '收起详情' : '展开详情'}
        </button>
      ) : null}

      {open ? (
        <div className={styles.details}>
          <div>{obs.knowledge.detail}</div>
          {obs.refresh.changedFiles.length > 0 ? (
            <>
              <div className={styles.metaLine}>最近写入（优先从 /workspace 重读）</div>
              <ul>
                {obs.refresh.changedFiles.map((path) => (
                  <li key={path} title={path}>
                    {basename(path)}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {obs.refresh.recentFailures.length > 0 ? (
            <>
              <div className={styles.metaLine}>近期工具失败</div>
              <ul>
                {obs.refresh.recentFailures.map((item, index) => (
                  <li key={`${item.tool}-${item.path || ''}-${index}`}>
                    {item.tool}
                    {item.path ? ` · ${basename(item.path)}` : ''}
                    {item.reason ? ` — ${item.reason}` : ''}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {obs.refresh.toolOffloadCount > 0 || obs.refresh.recentOffloads.length > 0 ? (
            <>
              <div className={styles.metaLine}>
                工具结果外置/截断（全文在 /large_tool_results/，可用 read_file 分段读取）
              </div>
              <ul>
                {obs.refresh.recentOffloads.length > 0
                  ? obs.refresh.recentOffloads.map((item, index) => (
                      <li key={`${item.tool}-off-${index}`}>
                        {item.tool}
                        {item.offloaded ? ' · 已外置' : ''}
                        {item.truncated ? ' · 已截断' : ''}
                        {item.path ? ` · ${item.path}` : ''}
                      </li>
                    ))
                  : [
                      <li key="off-count">
                        累计外置 {obs.refresh.toolOffloadCount} 次
                        {obs.refresh.toolTruncateCount > 0
                          ? `，截断 ${obs.refresh.toolTruncateCount} 次`
                          : ''}
                      </li>,
                    ]}
              </ul>
            </>
          ) : null}
          {obs.warnings.length > 0 ? (
            <>
              <div className={styles.metaLine}>warnings</div>
              <ul>
                {obs.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
