import {
  BranchesOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  CodeOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  FolderOpenOutlined,
  GithubOutlined,
  InfoCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Button, Tag, Tooltip } from 'antd';
import type { AgentConnectionState } from '../protocol/agentProtocol';
import type { AgentRuntimeState } from '../runtime/agentRuntime';
import {
  gateGapLabel,
  selectSessionProgress,
} from '../selectors/sessionProgress';
import { SESSION_STATUS_LABELS } from '../selectors/sessionStatus';
import styles from '../workbench/AgentWorkbench.module.css';
import AgentContextStatus from './AgentContextStatus';

interface AgentEnvironmentRailProps {
  state: AgentRuntimeState;
  connection: AgentConnectionState;
  connectionLabel: string;
  onOpenSettings: () => void;
}

function sessionStatusLabel(session: AgentRuntimeState['session']): string {
  const metadata = session?.metadata || {};
  const failureKind = typeof metadata.failure_kind === 'string' ? metadata.failure_kind : '';
  const nextAction = typeof metadata.next_action === 'string' ? metadata.next_action : '';
  const statusName = session?.status || '';
  if (
    (statusName === 'waiting_approval' || statusName === 'waiting_permission')
    && (nextAction === 'continue_approval' || metadata.recovered_after_restart === true)
  ) {
    return '请继续审批';
  }
  if (statusName === 'needs_manual_review' || statusName === 'failed') {
    if (failureKind === 'configuration_error' || nextAction === 'configure_model') return '需配置模型';
    if (failureKind === 'timeout') return '任务超时';
    if (failureKind === 'process_restart') return '可重新运行';
    if (failureKind === 'runtime_error') return '运行失败';
  }
  return SESSION_STATUS_LABELS[session?.status || 'idle'] || session?.status || '待命';
}

function basename(path?: string | null): string {
  if (!path) return '默认工作区';
  const segments = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return segments[segments.length - 1] || path;
}

function formatDelta(count: number, kind: 'positive' | 'negative'): string {
  if (count <= 0) return '0';
  return `${kind === 'positive' ? '+' : '-'}${count.toLocaleString()}`;
}

export default function AgentEnvironmentRail({
  state,
  connection,
  connectionLabel,
  onOpenSettings,
}: AgentEnvironmentRailProps) {
  const workspace = state.workspace;
  const session = state.session;
  const runtimePolicy = workspace?.runtime_policy || workspace?.runtime?.policy;
  const changedFiles = workspace?.changed_files || [];
  const additions = changedFiles.filter((file) => ['added', 'created', 'new'].includes(file.status)).length;
  const removals = changedFiles.filter((file) => ['deleted', 'removed'].includes(file.status)).length;
  const modified = changedFiles.length - additions - removals;
  const branch =
    session?.metadata?.git?.branch
    || workspace?.diagnostics?.git?.branch
    || runtimePolicy?.resource_profile?.agent?.branch
    || 'master';
  const provider = session?.provider || runtimePolicy?.provider || '本地';
  const model = session?.model || runtimePolicy?.model || '自动';
  const status = sessionStatusLabel(session);
  const mounts = workspace?.vfs_mounts || workspace?.runtime?.vfs_mounts || runtimePolicy?.vfs_mounts || [];
  const enabledTools = runtimePolicy?.tools?.allow_all_builtin
    ? '内置工具'
    : `${runtimePolicy?.tools?.allowed?.length || 0} 个工具`;
  const progress = selectSessionProgress(
    (session?.metadata || {}) as Record<string, unknown>,
  );
  const metrics = progress.metrics;
  const gate = progress.gate;
  const recovery = progress.recovery;

  return (
    <aside className={styles.environmentRail} aria-label="环境信息">
      <section className={styles.environmentCard}>
        <header className={styles.environmentHeader}>
          <span>环境信息</span>
          <Tooltip title="工作台设置">
            <Button
              type="text"
              size="small"
              icon={<SettingOutlined />}
              aria-label="打开工作台设置"
              onClick={onOpenSettings}
            />
          </Tooltip>
        </header>
        <div className={styles.environmentList}>
          <div className={styles.environmentRow}>
            <CodeOutlined />
            <span>变更</span>
            <strong>
              <span className={styles.changePositive}>{formatDelta(additions + modified, 'positive')}</span>
              <span className={styles.changeNegative}>{formatDelta(removals, 'negative')}</span>
            </strong>
          </div>
          <div className={styles.environmentRow}>
            <FolderOpenOutlined />
            <span>工作区</span>
            <Tooltip
              title={
                session?.project_path || workspace?.runtime?.workspace_root
                  ? `${session?.project_path || workspace?.runtime?.workspace_root}\n点击更换工作区`
                  : '点击选择本地工作区文件夹'
              }
            >
              <button
                type="button"
                className={styles.workspacePathChip}
                onClick={onOpenSettings}
                aria-label="打开工作区路径设置"
              >
                <span className={styles.workspacePathName}>
                  {basename(session?.project_path || workspace?.runtime?.workspace_root)}
                </span>
                <EditOutlined className={styles.workspacePathEdit} />
              </button>
            </Tooltip>
          </div>
          <div className={styles.environmentRow}>
            <BranchesOutlined />
            <span>分支</span>
            <strong>{String(branch)}</strong>
          </div>
          <div className={styles.environmentRow}>
            <CloudSyncOutlined />
            <span>提交或推送</span>
            <strong>{changedFiles.length > 0 ? `${changedFiles.length} 个文件` : '暂无变更'}</strong>
          </div>
          <div className={styles.environmentRow}>
            <GithubOutlined />
            <span>GitHub</span>
            <strong>{workspace?.diagnostics?.github_available === false ? 'CLI 不可用' : '未连接'}</strong>
          </div>
        </div>
      </section>

      <section className={styles.environmentCard}>
        <header className={styles.environmentHeader}>
          <span>运行状态</span>
          <Tag color={connection === 'open' ? 'green' : connection === 'error' ? 'red' : undefined}>
            {connectionLabel}
          </Tag>
        </header>
        <div className={styles.environmentList}>
          <div className={styles.environmentRow}>
            {session?.status === 'failed' ? <ExclamationCircleOutlined /> : <CheckCircleOutlined />}
            <span>会话</span>
            <strong>{status}</strong>
          </div>
          <div className={styles.environmentRow}>
            <InfoCircleOutlined />
            <span>模型</span>
            <strong>{provider}:{model}</strong>
          </div>
          <div className={styles.environmentRow}>
            <InfoCircleOutlined />
            <span>工具</span>
            <strong>{enabledTools}</strong>
          </div>
          <div className={styles.environmentRow}>
            <InfoCircleOutlined />
            <span>挂载</span>
            <strong>{mounts.length || 0}</strong>
          </div>
        </div>
      </section>

      <section className={styles.environmentCard} aria-label="上下文可观测">
        <header className={styles.environmentHeader}>
          <span>上下文</span>
        </header>
        <AgentContextStatus metadata={(session?.metadata || {}) as Record<string, unknown>} />
      </section>

      {progress.hasSignal ? (
        <section
          className={`${styles.environmentCard} ${styles.progressCard}`}
          aria-label="本轮运行指标"
        >
          <header className={styles.environmentHeader}>
            <span>本轮指标</span>
            {gate ? (
              <span
                className={`${styles.progressStatusPill} ${
                  gate.completedOk ? styles.progressStatusOk : styles.progressStatusGap
                }`}
              >
                <span className={styles.progressStatusDot} aria-hidden />
                {gate.completedOk ? '完成定义通过' : '完成有缺口'}
              </span>
            ) : metrics?.budgetHardBlocked ? (
              <span className={`${styles.progressStatusPill} ${styles.progressStatusGap}`}>
                <span className={styles.progressStatusDot} aria-hidden />
                探索预算耗尽
              </span>
            ) : metrics?.budgetSoftWarned ? (
              <span className={`${styles.progressStatusPill} ${styles.progressStatusWarn}`}>
                <span className={styles.progressStatusDot} aria-hidden />
                探索接近上限
              </span>
            ) : null}
          </header>

          {metrics ? (
            <div className={styles.progressMetricGrid}>
              <div className={styles.progressMetricCell}>
                <span>工具</span>
                <strong title={metrics.observeTotal ? `只读探索 ${metrics.observeTotal}` : undefined}>
                  {metrics.toolsTotal}
                  {metrics.toolsFailed > 0 ? (
                    <em className={styles.progressMetricSub}> / 失败 {metrics.toolsFailed}</em>
                  ) : null}
                </strong>
              </div>
              <div className={styles.progressMetricCell}>
                <span>验证</span>
                <strong
                  className={
                    metrics.verifyOk
                      ? styles.progressToneOk
                      : metrics.verifyAttempted
                        ? styles.progressToneDanger
                        : undefined
                  }
                >
                  {metrics.verifyOk ? '通过' : metrics.verifyAttempted ? '未通过' : '未执行'}
                </strong>
              </div>
              <div className={styles.progressMetricCell}>
                <span>轨迹</span>
                <strong className={metrics.trajectoryBlocks > 0 ? styles.progressToneWarn : undefined}>
                  {metrics.trajectoryBlocks}
                </strong>
              </div>
              <div className={styles.progressMetricCell}>
                <span>审批</span>
                <strong>{metrics.hitlCount}</strong>
              </div>
            </div>
          ) : null}

          {(recovery?.requireObservationBeforeRetry
            || metrics?.budgetSoftWarned
            || metrics?.budgetHardBlocked
            || gate) ? (
            <div className={styles.progressFooter}>
              {recovery?.requireObservationBeforeRetry ? (
                <Tooltip
                  title={
                    recovery.lastFailedCommand
                      ? `须先观察后再重试。上次失败命令：${recovery.lastFailedCommand}`
                      : '须先 read/grep 观察后再重试失败命令'
                  }
                >
                  <div className={`${styles.progressNote} ${styles.progressNoteWarn}`} role="note">
                    <ExclamationCircleOutlined />
                    <span>失败恢复：须先观察再重试</span>
                  </div>
                </Tooltip>
              ) : null}

              {metrics?.budgetHardBlocked || metrics?.budgetSoftWarned ? (
                <div
                  className={`${styles.progressNote} ${
                    metrics.budgetHardBlocked ? styles.progressNoteWarn : ''
                  }`}
                  role="note"
                >
                  <ExclamationCircleOutlined />
                  <span>
                    {metrics.budgetHardBlocked
                      ? '探索预算已耗尽，请收敛到修改与验证'
                      : '探索接近上限，建议减少扫描、聚焦改码'}
                  </span>
                </div>
              ) : null}

              {gate ? (
                <div className={styles.progressGateBlock}>
                  <div className={styles.progressGateRow}>
                    <span>完成定义</span>
                    <strong className={gate.completedOk ? styles.progressToneOk : styles.progressToneDanger}>
                      {gate.completedOk ? '已满足' : '未满足'}
                    </strong>
                  </div>
                  {gate.hasWrites ? (
                    <div className={styles.progressGateRow}>
                      <span>Diff 审阅</span>
                      <strong className={gate.diffVisible ? styles.progressToneOk : styles.progressToneDanger}>
                        {gate.diffVisible ? '可见' : '缺失'}
                      </strong>
                    </div>
                  ) : null}
                  {gate.gaps.length > 0 ? (
                    <div className={styles.progressGapList} title={gate.summary || undefined}>
                      {gate.gaps.slice(0, 3).map((gap) => (
                        <span key={gap} className={styles.progressGapChip}>
                          {gateGapLabel(gap)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {gate.writtenPaths.length > 0 ? (
                    <div className={styles.progressPaths} title={gate.writtenPaths.join('\n')}>
                      已写 {gate.writtenPaths.slice(0, 2).map((p) => p.split(/[/\\]/).pop()).join(' · ')}
                      {gate.writtenPaths.length > 2 ? ` +${gate.writtenPaths.length - 2}` : ''}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </aside>
  );
}
