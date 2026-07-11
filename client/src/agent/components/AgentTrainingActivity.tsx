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
    running: { statusLabel: '训练中', tone: 'running' },
    completed: { statusLabel: '已完成', tone: 'success' },
    failed: { statusLabel: '失败', tone: 'failure' },
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

function DetailList({ activity }: { activity: AgentTrainingActivity }) {
  const details: Array<[string, string]> = [];
  if (activity.kind === 'proposal' || activity.kind === 'submission') {
    details.push(['提案 ID', activity.proposalId]);
  }
  if (activity.kind === 'submission' && activity.taskId) details.push(['任务 ID', activity.taskId]);
  if (activity.kind === 'run_summary') {
    details.push(['任务 ID', activity.taskId]);
    if (activity.finalLoss !== undefined) details.push(['最终损失', activity.finalLoss.toFixed(4)]);
    if (activity.elapsedSeconds !== undefined) details.push(['耗时', formatDuration(activity.elapsedSeconds)]);
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
      <DetailList activity={activity} />
      {activity.kind === 'proposal' ? (
        <>
          <MessageList label="阻塞原因" messages={activity.blockers} />
          <MessageList label="注意事项" messages={activity.warnings} />
        </>
      ) : null}
    </section>
  );
}
