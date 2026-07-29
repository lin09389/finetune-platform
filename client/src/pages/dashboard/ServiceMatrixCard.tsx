import { ApiOutlined, CloudOutlined, DatabaseOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { motion } from 'framer-motion';
import { memo } from 'react';
import { GlassHoverCard, useMotionConfig } from '../../components/motion';
import { staggerItem } from '../../theme/motion-tokens';
import styles from '../Dashboard.module.css';

interface ServiceMatrixCardProps {
  backendConnected: boolean;
  ollamaAvailable: boolean;
  storageReady: boolean;
  storageStatusLabel: string;
}

/** Bento Card 2: 运行服务矩阵（API / Ollama / 存储 LED 状态） */
function ServiceMatrixCard({ backendConnected, ollamaAvailable, storageReady, storageStatusLabel }: ServiceMatrixCardProps) {
  const { getSafeVariants } = useMotionConfig();
  return (
    <motion.div variants={getSafeVariants(staggerItem)} style={{ height: '100%' }}>
      <GlassHoverCard className={styles.statCard}>
        <div className={styles.servicesMatrix}>
          <span className={styles.sectionTitle} style={{ marginBottom: 'var(--space-2)' }}>
            <ApiOutlined style={{ color: 'var(--accent-secondary)' }} />
            运行服务矩阵
          </span>
          <div className={styles.servicesGrid}>
            <div className={styles.serviceItem}>
              <span className={styles.serviceName}>
                <ThunderboltOutlined style={{ fontSize: 'var(--text-xs)' }} />
                API 核心服务
              </span>
              <div className={styles.serviceStatusArea}>
                <span className={styles.serviceStatusLabel}>
                  {backendConnected ? '已就绪' : '未连接'}
                </span>
                <span className={`${styles.ledIndicator} ${backendConnected ? styles.healthy : styles.error}`} />
              </div>
            </div>

            <div className={styles.serviceItem}>
              <span className={styles.serviceName}>
                <CloudOutlined style={{ fontSize: 'var(--text-xs)' }} />
                Ollama 实例
              </span>
              <div className={styles.serviceStatusArea}>
                <span className={styles.serviceStatusLabel}>
                  {ollamaAvailable ? '活跃' : '离线'}
                </span>
                <span className={`${styles.ledIndicator} ${ollamaAvailable ? styles.healthy : styles.warning}`} />
              </div>
            </div>

            <div className={styles.serviceItem}>
              <span className={styles.serviceName}>
                <DatabaseOutlined style={{ fontSize: 'var(--text-xs)' }} />
                存储健康
              </span>
              <div className={styles.serviceStatusArea}>
                <span className={styles.serviceStatusLabel}>
                  {storageStatusLabel}
                </span>
                <span className={`${styles.ledIndicator} ${storageReady ? styles.healthy : styles.error}`} />
              </div>
            </div>
          </div>
        </div>
      </GlassHoverCard>
    </motion.div>
  );
}

export default memo(ServiceMatrixCard);
