import { CheckCircleOutlined } from '@ant-design/icons';
import { Tag } from 'antd';
import { motion } from 'framer-motion';
import { memo } from 'react';
import { useMotionConfig } from '../../components/motion';
import GlassCard from '../../components/shared/GlassCard';
import { staggerItem } from '../../theme/motion-tokens';
import styles from '../Dashboard.module.css';
import type { ChainStep } from './types';

interface PipelineHealthCardProps {
  chainSteps: ChainStep[];
  readyStepCount: number;
  chainHealthPercent: number;
}

/** 工程闭环健康 - 虚线与流光折线可视化图 */
function PipelineHealthCard({ chainSteps, readyStepCount, chainHealthPercent }: PipelineHealthCardProps) {
  const { getSafeVariants, shouldReduceMotion } = useMotionConfig();
  return (
    <motion.div variants={getSafeVariants(staggerItem)} style={{ marginBottom: 'var(--space-8)' }}>
      <GlassCard intensity="medium" noHover className={styles.pipelineCard}>
        <div className={styles.historyHeader}>
          <span className={styles.sectionTitle} style={{ marginBottom: 0 }}>
            <CheckCircleOutlined style={{ color: 'var(--success)' }} />
            工程闭环健康
          </span>
          <Tag
            color={chainHealthPercent >= 80 ? 'success' : chainHealthPercent >= 50 ? 'warning' : 'default'}
            style={{ borderRadius: 'var(--radius-sm)', fontWeight: 700 }}
          >
            {readyStepCount}/{chainSteps.length} 节点就绪 ({chainHealthPercent}%)
          </Tag>
        </div>

        <div className={styles.pipelineFlowTrack}>
          <div className={styles.pipelineLineBackground} />
          {/* prefers-reduced-motion 时不渲染无限流光动画层 */}
          {chainHealthPercent > 0 && !shouldReduceMotion && <div className={styles.pipelineLaserFlow} />}

          <div className={styles.pipelineNodes}>
            {chainSteps.map((step, idx) => {
              const isReady = step.ready;
              return (
                <button
                  key={step.title}
                  type="button"
                  onClick={step.action}
                  className={`${styles.pipelineNode} ${isReady ? styles.nodeReady : styles.nodePending}`}
                >
                  <div className={styles.nodeIndicator}>
                    {idx + 1}
                    {isReady && <span className={styles.nodeBadge}>✓</span>}
                  </div>
                  <div className={styles.nodeTitle}>{step.title}</div>
                  <div className={styles.nodeValue}>{step.value}</div>
                </button>
              );
            })}
          </div>
        </div>
      </GlassCard>
    </motion.div>
  );
}

export default memo(PipelineHealthCard);
