import { DesktopOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Typography } from 'antd';
import { useEffect, useState } from 'react';
import {
  deriveDesktopOverallState,
  getDesktopRuntimeSnapshot,
  isDesktopRuntime,
  subscribeDesktopServiceStatuses,
} from '../../runtime/desktopRuntime';
import type {
  DesktopRuntimeDescriptor,
  DesktopServiceState,
  DesktopServiceStatus,
} from '../../types';
import styles from './DesktopRuntimeSection.module.css';

const STATE_LABELS: Record<DesktopServiceState, string> = {
  stopped: '已停止',
  starting: '启动中',
  ready: '就绪',
  degraded: '部分可用',
  failed: '异常',
  stopping: '停止中',
};

export default function DesktopRuntimeSection() {
  const desktop = isDesktopRuntime();
  const [runtime, setRuntime] = useState<DesktopRuntimeDescriptor | null>(null);
  const [services, setServices] = useState<DesktopServiceStatus[]>([]);
  const [overallState, setOverallState] = useState<DesktopServiceState>('starting');
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState<string | null>(null);

  useEffect(() => {
    if (!desktop) return undefined;
    let mounted = true;
    void getDesktopRuntimeSnapshot()
      .then((snapshot) => {
        if (!mounted || !snapshot) return;
        setRuntime(snapshot.runtime);
        setServices(snapshot.services);
        setOverallState(snapshot.overallState);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (mounted) setError(reason instanceof Error ? reason.message : '无法读取桌面运行时状态');
      });

    const unsubscribe = subscribeDesktopServiceStatuses((nextServices, nextState) => {
      if (!mounted) return;
      setServices(nextServices);
      setOverallState(nextState);
    });
    return () => {
      mounted = false;
      unsubscribe();
    };
  }, [desktop]);

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

  return (
    <section className={styles.section} aria-labelledby="desktop-runtime-title">
      <header className={styles.header}>
        <DesktopOutlined />
        <div className={styles.headingCopy}>
          <div className={styles.titleLine}>
            <h3 id="desktop-runtime-title">桌面运行时</h3>
            <span className={`${styles.status} ${styles[overallState]}`}>
              {STATE_LABELS[overallState]}
            </span>
          </div>
          <p>
            {runtime
              ? `${runtime.platform} ${runtime.arch} · App ${runtime.appVersion}`
              : '正在连接本地服务管理器'}
          </p>
        </div>
      </header>

      <div className={styles.serviceList}>
        {services.map((service) => (
          <div className={styles.serviceRow} key={service.id}>
            <span className={`${styles.dot} ${styles[service.state]}`} aria-hidden="true" />
            <div className={styles.serviceCopy}>
              <strong>{service.label}</strong>
              <span>
                {STATE_LABELS[service.state]}
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
