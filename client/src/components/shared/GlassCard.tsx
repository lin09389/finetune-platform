import React from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import styles from './GlassCard.module.css';

interface GlassCardProps extends HTMLMotionProps<'div'> {
  children: React.ReactNode;
  className?: string;
  intensity?: 'low' | 'medium' | 'high';
  noHover?: boolean;
}

const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className = '',
  intensity = 'medium',
  noHover = false,
  ...props
}) => {
  const intensityClass = styles[`intensity-${intensity}`];
  
  return (
    <motion.div
      className={`${styles.glassCard} ${intensityClass} ${className}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={!noHover ? { y: -4, transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] } } : undefined}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      {...props}
    >
      <div className={styles.reflection} />
      <div className={styles.content}>
        {children}
      </div>
    </motion.div>
  );
};

export default GlassCard;
