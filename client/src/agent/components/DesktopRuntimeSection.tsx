import { DesktopOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import {
  deriveDesktopOverallState,
  getDesktopRuntimeSnapshot,
  isDesktopRuntime,
  prepareBaseRuntime,
  repairBaseRuntime,
  revealRuntimeLogs,
  retryRuntimeOperation,
  subscribeDesktopServiceStatuses,
  subscribeManagedRuntimeStatus,
} from '../../runtime/desktopRuntime';
import type {
  DesktopRuntimeDescriptor,
  DesktopServiceState,
  DesktopServiceStatus,
  ManagedRuntimeState,
  ManagedRuntimeStatus,
} from '../../types';
import styles from './DesktopRuntimeSection.module.css';

const SERVICE_STATE_LABELS: Record<DesktopServiceState, string> = {
  stopped: '已停止',
  starting: '启动中',
  ready: '就绪',
  degraded: '部分可用',
  failed: '异常',
  stopping: '停止中',
};

const RUNTIME_STATE_LABELS: Record<ManagedRuntimeState, string> = {
  unavailable: '未准备',
  checking: '检查中',
  preparing: '准备中',
  verifying: '验证中',
  ready: '已就绪',
  repair_required: '需要修复',
  failed: '准备失败',
};

const RUNTIME_ERROR_COPY: Record<string, string> = {
  ARCHIVE_CORRUPT: '运行时包已损坏，请修复后重试。',
  DISK_SPACE_LOW: '磁盘空间不足，请释放空间后重试。',
  PERMISSION_DENIED: '无法写入运行时目录，请检查权限后重试。',
  ANTIVIRUS_LOCK: '文件正被安全软件占用，请稍后重试。',
  HEALTH_PROBE_FAILED: '运行时验证未通过，上一版本仍会保留。',
  MANAGED_RUNTIME_ARTIFACT_UNAVAILABLE: '未找到兼容的基础运行时包，请检查本地制品配置。',
  MANAGED_RUNTIME_ARTIFACT_AMBIGUOUS: '检测到多个兼容运行时包，请只保留一个候选版本。',
  MANAGED_RUNTIME_ARCHIVE_DIGEST_MISMATCH: '运行时包校验失败，未替换当前可用版本。',
  MANAGED_RUNTIME_UNPACKED_DIGEST_MISMATCH: '运行时解压内容校验失败，已保留当前可用版本。',
  MANAGED_RUNTIME_PROBE_INCOMPATIBLE: '运行时不是兼容的 Python 3.11，未执行激活。',
};

type RuntimeAction = 'prepare' | 'repair' | 'retry' | 'logs' | null;

const isBusyRuntimeState = (state: ManagedRuntimeState | undefined) => (
  state === 'checking' || state === 'preparing' || state === 'verifying'
);

const describeRuntime = (runtime: ManagedRuntimeStatus | null): string => {
  if (!runtime) return '正在读取基础运行时状态';
  if (runtime.state === 'ready') {
    const version = runtime.runtimeVersion || '当前版本';
    const python = runtime.pythonVersion ? ` · Python ${runtime.pythonVersion}` : '';
    return `基础运行时 ${version}${python}`;
  }
  if (runtime.state === 'preparing' && runtime.progress) {
    return '正在准备基础运行时';
  }
  if (runtime.state === 'verifying') return '正在验证基础运行时完整性与健康状态';
  if (runtime.state === 'checking') return '正在检查已安装的基础运行时';
  return RUNTIME_ERROR_COPY[runtime.lastErrorCode || ''] || '基础运行时尚未就绪，可随时准备或修复。';
};

export default function DesktopRuntimeSection() {
  const desktop = isDesktopRuntime();
  const [runtime, setRuntime] = useState<DesktopRuntimeDescriptor | null>(null);
  const [services, setServices] = useState<DesktopServiceStatus[]>([]);
  const [managedRuntime, setManagedRuntime] = useState<ManagedRuntimeStatus | null>(null);
  const [overallState, setOverallState] = useState<DesktopServiceState>('starting');
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState<string | null>(null);
  const [runtimeAction, setRuntimeAction] = useState<RuntimeAction>(null);

  useEffect(() => {
    if (!desktop) return undefined;
    let mounted = true;
    void getDesktopRuntimeSnapshot()
      .then((snapshot) => {
        if (!mounted || !snapshot) return;
        setRuntime(snapshot.runtime);
        setServices(snapshot.services);
        setManagedRuntime(snapshot.managedRuntime);
        setOverallState(snapshot.overallState);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (mounted) setError(reason instanceof Error ? reason.message : '无法读取桌面运行时状态');
      });

    const unsubscribeServices = subscribeDesktopServiceStatuses((nextServices, nextState) => {
      if (!mounted) return;
      setServices(nextServices);
      setOverallState(nextState);
    });
    const unsubscribeRuntime = subscribeManagedRuntimeStatus((nextRuntime) => {
      if (!mounted) return;
      setManagedRuntime(nextRuntime);
      setError(null);
    });
    return () => {
      mounted = false;
      unsubscribeServices();
      unsubscribeRuntime();
    };
  }, [desktop]);

  const runtimeBusy = isBusyRuntimeState(managedRuntime?.state);
  const runtimeProgress = useMemo(() => {
    if (!managedRuntime?.progress) return null;
    return Math.round((managedRuntime.progress.completed / managedRuntime.progress.total) * 100);
  }, [managedRuntime]);

  if (!desktop) return null;

  const restart = async (serviceId: string) => {
    if (!window.electronAPI) return;
    setRestarting(serviceId);
    setError(null);
    try {
      const nextServices = await window.electronAPI.restartService(serviceId);
      setServices(nextServices);
      setOverallState(deriveDesktopOverallState(nextServices));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '服务重启失败');
    } finally {
      setRestarting(null);
    }
  };

  const runRuntimeAction = async (action: Exclude<RuntimeAction, null>) => {
    setRuntimeAction(action);
    setError(null);
    try {
      if (action === 'prepare') setManagedRuntime(await prepareBaseRuntime());
      if (action === 'repair') setManagedRuntime(await repairBaseRuntime());
      if (action === 'retry') setManagedRuntime(await retryRuntimeOperation());
      if (action === 'logs') await revealRuntimeLogs();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '运行时操作失败，请查看日志后重试。');
    } finally {
      setRuntimeAction(null);
    }
  };

  const renderRuntimeActions = () => {
    const disabled = runtimeBusy || runtimeAction !== null;
    if (!managedRuntime || runtimeBusy) {
      return (
        <Button size="small" loading disabled aria-label="正在准备运行时">
          正在准备运行时
        </Button>
      );
    }
    if (managedRuntime.state === 'unavailable') {
      return (
        <Button size="small" type="primary" disabled={disabled} loading={runtimeAction === 'prepare'} aria-label="准备基础运行时" onClick={() => void runRuntimeAction('prepare')}>
          准备运行时
        </Button>
      );
    }
    if (managedRuntime.state === 'repair_required') {
      return (
        <Button size="small" disabled={disabled} loading={runtimeAction === 'repair'} aria-label="修复基础运行时" onClick={() => void runRuntimeAction('repair')}>
          修复运行时
        </Button>
      );
    }
    if (managedRuntime.state === 'failed' && managedRuntime.recoverable) {
      return (
        <Button size="small" disabled={disabled} loading={runtimeAction === 'retry'} aria-label="重试运行时操作" onClick={() => void runRuntimeAction('retry')}>
          重试
        </Button>
      );
    }
    return null;
  };

  return (
    <section className={styles.section} aria-labelledby="desktop-runtime-title">
      <header className={styles.header}>
        <DesktopOutlined />
        <div className={styles.headingCopy}>
          <div className={styles.titleLine}>
            <h3 id="desktop-runtime-title">桌面运行时</h3>
            <span className={`${styles.status} ${styles[overallState]}`}>
              {SERVICE_STATE_LABELS[overallState]}
            </span>
          </div>
          <p>
            {runtime
              ? `${runtime.platform} ${runtime.arch} · App ${runtime.appVersion}`
              : '正在连接本地服务管理器'}
          </p>
        </div>
      </header>

      <div className={styles.managedRuntime} aria-live="polite">
        <div className={styles.managedRuntimeCopy}>
          <span className={`${styles.dot} ${styles[managedRuntime?.state || 'checking']}`} aria-hidden="true" />
          <div>
            <strong>基础运行时</strong>
            <span>{describeRuntime(managedRuntime)}</span>
            {managedRuntime?.state === 'ready' ? <small>重启应用后，本地服务将使用此运行时。</small> : null}
          </div>
        </div>
        <span className={`${styles.runtimeStatus} ${styles[managedRuntime?.state || 'checking']}`}>
          {managedRuntime ? RUNTIME_STATE_LABELS[managedRuntime.state] : '检查中'}
        </span>
        {runtimeProgress !== null ? (
          <div className={styles.progressTrack} role="progressbar" aria-label="基础运行时准备进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={runtimeProgress}>
            <span style={{ width: `${runtimeProgress}%` }} />
          </div>
        ) : null}
        <div className={styles.runtimeActions}>
          {renderRuntimeActions()}
          {(managedRuntime?.state !== 'ready' && managedRuntime?.state !== 'unavailable') ? (
            <Button type="text" size="small" disabled={runtimeAction !== null} loading={runtimeAction === 'logs'} aria-label="查看运行时日志" onClick={() => void runRuntimeAction('logs')}>
              查看日志
            </Button>
          ) : null}
        </div>
      </div>

      <div className={styles.serviceList}>
        {services.map((service) => (
          <div className={styles.serviceRow} key={service.id}>
            <span className={`${styles.dot} ${styles[service.state]}`} aria-hidden="true" />
            <div className={styles.serviceCopy}>
              <strong>{service.label}</strong>
              <span>
                {SERVICE_STATE_LABELS[service.state]}
                {service.pid ? ` · PID ${service.pid}` : ''}
                {service.restarts > 0 ? ` · 已恢复 ${service.restarts} 次` : ''}
              </span>
              {service.lastError ? <small>{service.lastError}</small> : null}
            </div>
            {service.state === 'failed' || service.state === 'degraded' || service.state === 'stopped' ? (
              <Button
                type="text"
                size="small"
                icon={<ReloadOutlined />}
                loading={restarting === service.id}
                aria-label={`重启${service.label}`}
                onClick={() => void restart(service.id)}
              />
            ) : null}
          </div>
        ))}
        {services.length === 0 && !error ? (
          <Typography.Text type="secondary" className={styles.empty}>
            正在等待控制面、训练 Worker 与推理服务上报状态。
          </Typography.Text>
        ) : null}
      </div>

      {error ? <div className={styles.error} role="alert">{error}</div> : null}
    </section>
  );
}
