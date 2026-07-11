import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import type { AgentTrainingActivity } from '../protocol/agentProtocol';
import styles from '../workbench/AgentWorkbench.module.css';

interface TrainingActivityPresentation {
  title: string;
  statusLabel: string;
  tone: 'ready' | 'warning' | 'blocked' | 'pending' | 'running' | 'success' | 'failure' | 'unknown';
}

function presentationFor(activity: AgentTrainingActivity): TrainingActivityPresentation {
  const title = activity.kind === 'proposal'
    ? '训练提案'
    : activity.kind === 'submission'
      ? '训练提交'
      : '训练运行';
  const known = {
    ready: { statusLabel: '可以提交审批', tone: 'ready' },
    warning: { statusLabel: '存在提醒', tone: 'warning' },
    blocked: { statusLabel: '已阻塞', tone: 'blocked' },
    waiting_approval: { statusLabel: '等待审批', tone: 'pending' },
    submitted: { statusLabel: '已提交', tone: 'success' },
    queued: { statusLabel: '已排队', tone: 'pending' },
    loading: { statusLabel: '加载中', tone: 'pending' },
    running: { statusLabel: '训练中', tone: 'running' },
    completed: { statusLabel: '已完成', tone: 'success' },
    failed: { statusLabel: '失败', tone: 'failure' },
    missing: { statusLabel: '任务记录暂不可用', tone: 'warning' },
    degraded: { statusLabel: '进度同步暂时不可用', tone: 'warning' },
  } as const;
  const state = known[activity.status as keyof typeof known];
  return state ? { title, ...state } : { title, statusLabel: `状态：${activity.status}`, tone: 'unknown' };
}

function statusIcon(tone: TrainingActivityPresentation['tone']) {
  if (tone === 'running') return <LoadingOutlined spin aria-hidden="true" />;
  if (tone === 'success' || tone === 'ready') return <CheckCircleOutlined aria-hidden="true" />;
  if (tone === 'failure' || tone === 'blocked') return <CloseCircleOutlined aria-hidden="true" />;
  if (tone === 'warning') return <ExclamationCircleOutlined aria-hidden="true" />;
  if (tone === 'pending') return <ClockCircleOutlined aria-hidden="true" />;
  return <SafetyCertificateOutlined aria-hidden="true" />;
}

function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole}s`;
  return `${Math.floor(whole / 60)}m ${(whole % 60).toString().padStart(2, '0')}s`;
}

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return date.toISOString().replace('T', ' ').replace('.000Z', ' UTC');
}

function displayStep(step: number | undefined, totalSteps: number): number {
  return Math.min(totalSteps, Math.max(0, step ?? 0));
}

function TrainingProgress({ activity }: { activity: AgentTrainingActivity }) {
  if (activity.kind !== 'run_summary') return null;
  const totalSteps = activity.totalSteps;
  if (totalSteps === undefined || totalSteps <= 0) {
    if (['completed', 'failed', 'missing', 'degraded'].includes(activity.status)) return null;
    return (
      <div className={styles.trainingActivityProgress}>
        <span>训练进度</span>
        <div
          className={styles.trainingActivityProgressIndeterminate}
          role="progressbar"
          aria-label="训练进度（未知）"
          aria-valuetext="进度待定"
        />
        <span>等待任务报告总步数</span>
      </div>
    );
  }

  const step = displayStep(activity.step, totalSteps);
  const percent = Math.round((step / totalSteps) * 100);
  return (
    <div className={styles.trainingActivityProgress}>
      <span>训练进度</span>
      <progress
        className={styles.trainingActivityProgressTrack}
        aria-label="训练进度"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        value={percent}
        max={100}
      >
        {percent}%
      </progress>
      <span>{step}/{totalSteps} · {percent}%</span>
    </div>
  );
}

function DetailList({ activity }: { activity: AgentTrainingActivity }) {
  const details: Array<[string, string]> = [];
  if (activity.kind === 'proposal' || activity.kind === 'submission') {
    details.push(['提案 ID', activity.proposalId]);
  }
  if (activity.kind === 'submission' && activity.taskId) details.push(['任务 ID', activity.taskId]);
  if (activity.kind === 'run_summary') {
    details.push(['任务 ID', activity.taskId]);
    if (activity.finalLoss !== undefined) details.push(['最终损失', activity.finalLoss.toFixed(4)]);
    if (activity.phase) details.push(['阶段', activity.phase]);
    if (activity.epoch !== undefined) details.push(['轮次', String(activity.epoch)]);
    if (activity.loss !== undefined) details.push(['损失', activity.loss.toFixed(4)]);
    if (activity.elapsedSeconds !== undefined) details.push(['耗时', formatDuration(activity.elapsedSeconds)]);
    if (activity.etaSeconds !== undefined) details.push(['预计剩余', formatDuration(activity.etaSeconds)]);
    if (activity.updatedAt) details.push(['最后更新', formatUpdatedAt(activity.updatedAt)]);
  }
  if (activity.modelId) details.push(['模型', activity.modelId]);
  if (activity.datasetId) details.push(['数据集', activity.datasetId]);
  if (activity.method) details.push(['方法', activity.method]);
  if (details.length === 0) return null;
  return (
    <dl className={styles.trainingActivityDetails}>
      {details.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function MessageList({ label, messages }: { label: string; messages: string[] }) {
  if (messages.length === 0) return null;
  return (
    <div className={styles.trainingActivityMessages}>
      <strong>{label}</strong>
      <ul>
        {messages.map((message, index) => <li key={`${index}:${message}`}>{message}</li>)}
      </ul>
    </div>
  );
}

export default function AgentTrainingActivity({ activity }: { activity: AgentTrainingActivity }) {
  const presentation = presentationFor(activity);
  return (
    <section
      className={`${styles.trainingActivityCard} ${styles[`trainingActivity_${presentation.tone}`]}`}
      aria-label={`训练活动：${presentation.title}`}
    >
      <div className={styles.trainingActivityHeader}>
        <div>
          <h3>{presentation.title}</h3>
          <span className={styles.trainingActivitySource}>{activity.sourceTool}</span>
        </div>
        <span className={styles.trainingActivityStatus} role="status" aria-live="polite">
          {statusIcon(presentation.tone)} {presentation.statusLabel}
        </span>
      </div>
      <p className={styles.trainingActivitySummary}>{activity.summary}</p>
      <TrainingProgress activity={activity} />
      <DetailList activity={activity} />
      {activity.kind === 'run_summary' && activity.status === 'completed' && activity.artifactAvailable ? (
        <p className={styles.trainingActivityHandoff}>
          训练产物已可用。<a href={`/training?task_id=${encodeURIComponent(activity.taskId)}`}>在模型/训练中查看</a>
        </p>
      ) : null}
      {activity.kind === 'proposal' ? (
        <>
          <MessageList label="阻塞原因" messages={activity.blockers} />
          <MessageList label="注意事项" messages={activity.warnings} />
        </>
      ) : null}
    </section>
  );
}
