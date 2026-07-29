import { ArrowRightOutlined, FolderOutlined } from '@ant-design/icons';
import { motion } from 'framer-motion';
import { memo } from 'react';
import { GlassHoverCard, useMotionConfig } from '../../components/motion';
import { CountUp } from '../../components/shared/MotionWrapper';
import { staggerItem } from '../../theme/motion-tokens';
import styles from '../Dashboard.module.css';

interface AssetSummaryCardProps {
  availableModelCount: number;
  datasetCount: number;
  onGoModels: () => void;
  onGoDatasets: () => void;
}

/** Bento Card 3: 平台资产仓（模型 / 数据集数量与入口） */
function AssetSummaryCard({ availableModelCount, datasetCount, onGoModels, onGoDatasets }: AssetSummaryCardProps) {
  const { getSafeVariants } = useMotionConfig();
  return (
    <motion.div variants={getSafeVariants(staggerItem)} style={{ height: '100%' }}>
      <GlassHoverCard className={styles.statCard}>
        <div className={styles.assetStatusCard}>
          <span className={styles.sectionTitle}>
            <FolderOutlined style={{ color: 'var(--warning)' }} />
            平台资产仓
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <div className={styles.assetStats}>
              <div>
                <span className={styles.assetTitle}>可用模型</span>
                <div className={styles.assetMainNumber} style={{ color: 'var(--accent-primary)' }}>
                  <CountUp value={availableModelCount} />
                </div>
              </div>
              <button onClick={onGoModels} className={styles.assetActionBtn}>
                管理 <ArrowRightOutlined style={{ fontSize: 10 }} />
              </button>
            </div>
            <div style={{ height: 1, background: 'var(--border-color)' }} />
            <div className={styles.assetStats}>
              <div>
                <span className={styles.assetTitle}>导入数据集</span>
                <div className={styles.assetMainNumber} style={{ background: 'var(--gradient-warm)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                  <CountUp value={datasetCount} />
                </div>
              </div>
              <button onClick={onGoDatasets} className={styles.assetActionBtn}>
                导入 <ArrowRightOutlined style={{ fontSize: 10 }} />
              </button>
            </div>
          </div>
        </div>
      </GlassHoverCard>
    </motion.div>
  );
}

export default memo(AssetSummaryCard);
