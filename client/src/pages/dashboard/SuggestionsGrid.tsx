import { CheckCircleOutlined, ExclamationCircleOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { motion } from 'framer-motion';
import { memo } from 'react';
import { InteractiveButton, useMotionConfig } from '../../components/motion';
import GlassCard from '../../components/shared/GlassCard';
import { staggerItem } from '../../theme/motion-tokens';
import styles from '../Dashboard.module.css';
import type { Suggestion } from './types';

interface SuggestionsGridProps {
  suggestions: Suggestion[];
}

const suggestionIcon = (type: Suggestion['type']) => {
  if (type === 'warning') return <ExclamationCircleOutlined />;
  if (type === 'success') return <CheckCircleOutlined />;
  return <InfoCircleOutlined />;
};

const suggestionColor = (type: Suggestion['type']) => {
  if (type === 'warning') return 'var(--warning)';
  if (type === 'success') return 'var(--success)';
  return 'var(--info)';
};

/** 下一步建议卡片网格 */
function SuggestionsGrid({ suggestions }: SuggestionsGridProps) {
  const { getSafeVariants } = useMotionConfig();
  return (
    <div style={{ marginBottom: 'var(--space-8)' }}>
      <h3 className={styles.sectionTitle}>
        <InfoCircleOutlined style={{ color: 'var(--info)' }} />
        下一步建议
      </h3>
      <div className={styles.suggestionsGrid}>
        {suggestions.map((suggestion, index) => {
          const color = suggestionColor(suggestion.type);
          return (
            <motion.div variants={getSafeVariants(staggerItem)} key={index} style={{ height: '100%' }}>
              <GlassCard
                intensity="low"
                style={{
                  height: '100%',
                  borderTop: `3px solid ${color}`,
                  padding: 'var(--space-5)',
                }}
              >
                <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'flex-start' }}>
                  <div style={{ fontSize: 'var(--text-xl)', color, marginTop: 'var(--space-0-5)' }}>
                    {suggestionIcon(suggestion.type)}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontWeight: 'var(--font-bold)',
                        color: 'var(--text-primary)',
                        marginBottom: 'var(--space-1-5)',
                        fontSize: 'var(--text-base)',
                      }}
                    >
                      {suggestion.title}
                    </div>
                    <div
                      style={{
                        color: 'var(--text-secondary)',
                        fontSize: 'var(--text-sm)',
                        lineHeight: 'var(--leading-normal)',
                        marginBottom: suggestion.action ? 'var(--space-4)' : 0,
                      }}
                    >
                      {suggestion.desc}
                    </div>
                    {suggestion.action && (
                      <InteractiveButton
                        variant="primary"
                        onClick={suggestion.action}
                        style={{ borderRadius: 'var(--radius-sm)', fontWeight: 'var(--font-semibold)', padding: 'var(--space-1) var(--space-3)', fontSize: 'var(--text-sm)', height: '32px' }}
                      >
                        {suggestion.buttonText}
                      </InteractiveButton>
                    )}
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

export default memo(SuggestionsGrid);
