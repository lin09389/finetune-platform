import { PlayCircleOutlined } from '@ant-design/icons';
import { motion } from 'framer-motion';
import { memo } from 'react';
import type { KeyboardEvent } from 'react';
import { GlassHoverCard, useMotionConfig } from '../../components/motion';
import { staggerItem } from '../../theme/motion-tokens';
import styles from '../Dashboard.module.css';
import type { MainAction } from './types';

interface MainActionsGridProps {
  actions: MainAction[];
}

/** 令牌色 + 透明度：color 是 var(--x) 形式，不能用 hex alpha 后缀拼接 */
const withAlpha = (color: string, percent: number) =>
  `color-mix(in srgb, ${color} ${percent}%, transparent)`;

/** 主要操作入口卡片网格（可点击卡片带键盘支持） */
function MainActionsGrid({ actions }: MainActionsGridProps) {
  const { getSafeVariants } = useMotionConfig();

  const onActivateKey = (event: KeyboardEvent, action: () => void) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      action();
    }
  };

  return (
    <div style={{ marginBottom: 'var(--space-8)' }}>
      <h3 className={styles.sectionTitle}>
        <PlayCircleOutlined style={{ color: 'var(--accent-primary)' }} />
        主要操作入口
      </h3>
      <div className={styles.bentoGrid}>
        {actions.map((action) => (
          <div key={action.title} className={styles['span-3']}>
            <motion.div variants={getSafeVariants(staggerItem)} style={{ height: '100%' }}>
              <GlassHoverCard
                className={styles.quickActionCard}
                role="button"
                tabIndex={0}
                aria-label={action.title}
                onClick={action.onClick}
                onKeyDown={(event) => onActivateKey(event, action.onClick)}
                style={{
                  '--spotlight-color': withAlpha(action.color, 8),
                  '--spotlight-border': withAlpha(action.color, 21),
                } as React.CSSProperties}
              >
                <div
                  className={styles.quickActionIcon}
                  style={{
                    background: withAlpha(action.color, 7),
                    color: action.color,
                    border: `1px solid ${withAlpha(action.color, 15)}`,
                  }}
                >
                  {action.icon}
                </div>
                <div>
                  <div className={styles.quickActionTitle}>{action.title}</div>
                  <div className={styles.quickActionDesc}>{action.description}</div>
                </div>
              </GlassHoverCard>
            </motion.div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default memo(MainActionsGrid);
