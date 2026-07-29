import { DesktopOutlined } from '@ant-design/icons';
import { motion } from 'framer-motion';
import { memo } from 'react';
import { GlassHoverCard, useMotionConfig } from '../../components/motion';
import { CountUp } from '../../components/shared/MotionWrapper';
import { staggerItem } from '../../theme/motion-tokens';
import styles from '../Dashboard.module.css';

interface DeviceConsoleCardProps {
  vramUsed: number;
  vramTotal: number;
  vramPercent: number;
  memUsed: number;
  memTotal: number;
  memPercent: number;
}

/** Bento Card 1: 硬件设备控制台（VRAM / 内存占用条） */
function DeviceConsoleCard({ vramUsed, vramTotal, vramPercent, memUsed, memTotal, memPercent }: DeviceConsoleCardProps) {
  const { getSafeVariants } = useMotionConfig();
  return (
    <motion.div variants={getSafeVariants(staggerItem)} style={{ height: '100%' }}>
      <GlassHoverCard className={styles.statCard}>
        <div className={styles.deviceConsole}>
          <div className={styles.deviceTitleArea}>
            <span className={styles.sectionTitle} style={{ marginBottom: 0 }}>
              <DesktopOutlined style={{ color: 'var(--info)' }} />
              硬件设备控制台
            </span>
          </div>

          <div className={styles.deviceMetricsGrid}>
            {/* VRAM Meter */}
            <div className={styles.metricProgressArea}>
              <div className={styles.metricHeader}>
                <span className={styles.metricTitle}>GPU 显存占用</span>
                <span className={styles.metricValue}>
                  <CountUp value={vramUsed} decimals={1} />
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 'var(--font-medium)' }}>
                     / {vramTotal} GB
                  </span>
                </span>
              </div>
              <div className={styles.metricBarContainer}>
                <div
                  className={styles.metricBarFill}
                  style={{
                    width: `${vramPercent}%`,
                    background: vramPercent > 90
                      ? 'var(--gradient-error)'
                      : vramPercent > 75
                        ? 'var(--gradient-warning)'
                        : 'var(--gradient-brand)',
                    transition: `width 0.8s var(--ease-smooth), background 0.6s var(--ease-smooth)`,
                  }}
                />
              </div>
              <span style={{ fontSize: 'var(--text-xs)', textAlign: 'right', display: 'flex', alignItems: 'center', gap: 'var(--space-1-5)' }}>
                <span style={{ color: 'var(--text-tertiary)' }}>已占用 {vramPercent}%</span>
                {vramPercent > 90 && (
                  <span style={{ color: 'var(--error)', fontWeight: 'var(--font-semibold)', fontSize: 'var(--text-2xs, 10px)', padding: '1px 6px', background: 'var(--error-light)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--error-border)' }}>危险</span>
                )}
                {vramPercent > 75 && vramPercent <= 90 && (
                  <span style={{ color: 'var(--warning)', fontWeight: 'var(--font-semibold)', fontSize: 'var(--text-2xs, 10px)', padding: '1px 6px', background: 'var(--warning-light)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--warning-border)' }}>警告</span>
                )}
              </span>
            </div>

            {/* System Memory Meter */}
            <div className={styles.metricProgressArea}>
              <div className={styles.metricHeader}>
                <span className={styles.metricTitle}>系统内存占用</span>
                <span className={styles.metricValue}>
                  <CountUp value={memUsed} decimals={1} />
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', fontWeight: 'var(--font-medium)' }}>
                     / {memTotal} GB
                  </span>
                </span>
              </div>
              <div className={styles.metricBarContainer}>
                <div
                  className={styles.metricBarFill}
                  style={{
                    width: `${memPercent}%`,
                    background: 'var(--accent-secondary)',
                  }}
                />
              </div>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', textAlign: 'right' }}>
                已占用 {memPercent}%
              </span>
            </div>
          </div>
        </div>
      </GlassHoverCard>
    </motion.div>
  );
}

export default memo(DeviceConsoleCard);
