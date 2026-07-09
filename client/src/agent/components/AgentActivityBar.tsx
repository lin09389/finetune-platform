import { Tooltip } from 'antd';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { useMotionConfig } from '../../components/motion/useMotionConfig';
import type { AgentActivity } from '../selectors/currentActivity';
import type { AgentConnectionState } from '../protocol/agentProtocol';
import styles from '../workbench/AgentWorkbench.module.css';

interface AgentActivityBarProps {
  /** 当前活动；为 null 但 session 运行中时显示「等待首个输出」兜底 */
  activity: AgentActivity | null;
  /** session 是否处于运行态 */
  isRunning: boolean;
  /** timeline 是否为空（用于决定兜底文案） */
  timelineEmpty: boolean;
  /** 连接状态，用于右侧 mini 指示 */
  connection: AgentConnectionState;
  connectionLabel: string;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remaining.toString().padStart(2, '0')}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${(minutes % 60).toString().padStart(2, '0')}m`;
}

const CONNECTION_DOT_CLASS: Record<AgentConnectionState, string | undefined> = {
  idle: styles.activityDotIdle,
  connecting: styles.activityDotConnecting,
  open: styles.activityDotOpen,
  reconnecting: styles.activityDotReconnecting,
  closed: styles.activityDotClosed,
  error: styles.activityDotError,
};

/**
 * 运行时活动状态栏：固定在时间线上方，让用户随时知道
 * 「Agent 正在做什么、已经跑了多久、连接是否健康」。
 *
 * - 有 currentActivity 时显示具体活动（正在调用工具 read_file / 正在规划 / ...）
 * - 无 currentActivity 但 session 运行中且 timeline 为空时，显示「等待首个输出」兜底
 * - session 非运行态时整个 bar 不渲染
 * - 脉动动画经 useMotionConfig 尊重 prefers-reduced-motion
 */
export default function AgentActivityBar({
  activity,
  isRunning,
  timelineEmpty,
  connection,
  connectionLabel,
}: AgentActivityBarProps) {
  const { shouldReduceMotion } = useMotionConfig();
  const [now, setNow] = useState(Date.now());

  // 每秒刷新计时器；仅在运行态时计时
  useEffect(() => {
    if (!isRunning || !activity?.startedAt) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isRunning, activity?.startedAt]);

  // 非运行态时保留占位高度，避免 timeline 上下抖动
  if (!isRunning) {
    return <div className={styles.activityBarPlaceholder} aria-hidden="true" />;
  }

  const label = activity?.label
    || (timelineEmpty ? 'Agent 已开始处理，等待首个输出...' : '正在处理');
  const detail = activity?.detail;
  const elapsed = activity?.startedAt
    ? Math.max(0, Math.floor((now - activity.startedAt) / 1000))
    : null;

  return (
    <div className={styles.activityBar} role="status" aria-live="polite">
      <span className={styles.activityPulse}>
        <motion.span
          className={styles.activityPulseDot}
          animate={shouldReduceMotion ? undefined : { scale: [1, 1.4, 1], opacity: [1, 0.5, 1] }}
          transition={shouldReduceMotion ? undefined : { duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
        />
      </span>
      <span className={styles.activityLabel}>
        {label}
        {detail ? <span className={styles.activityDetail}>{detail}</span> : null}
      </span>
      {elapsed !== null ? (
        <span className={styles.activityTimer} aria-label="已运行时长">
          {formatElapsed(elapsed)}
        </span>
      ) : null}
      <Tooltip title={connectionLabel}>
        <span className={`${styles.activityConnectionDot} ${CONNECTION_DOT_CLASS[connection] || ''}`} />
      </Tooltip>
    </div>
  );
}
