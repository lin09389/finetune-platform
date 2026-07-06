import { HTMLMotionProps, motion, useReducedMotion } from 'framer-motion';
import React from 'react';
import styles from './GlassCard.module.css';

interface GlassCardProps extends HTMLMotionProps<'div'> {
  children: React.ReactNode;
  className?: string;
  intensity?: 'low' | 'medium' | 'high';
  noHover?: boolean;
}

/**
 * GlassCard — Claude-style paper card.
 *
 * Claude's cards are quiet and editorial: a warm paper surface with
 * a subtle border and the gentlest shadow. No mouse-tracking
 * spotlights, no glass reflections, no flashy hover effects — just
 * a calm, typeset feel where content leads.
 */
const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className = '',
  intensity = 'medium',
  noHover = false,
  ...props
}) => {
  const intensityClass = styles[`intensity-${intensity}`];
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      className={`${styles.glassCard} ${intensityClass} ${className}`}
      initial={reduceMotion ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={
        !noHover && !reduceMotion
          ? { y: -1, transition: { type: 'tween', duration: 0.2, ease: [0.23, 1, 0.32, 1] as const } }
          : undefined
      }
      transition={reduceMotion ? { duration: 0 } : { duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
      {...props}
    >
      <div className={styles.content}>{children}</div>
    </motion.div>
  );
};

export default GlassCard;
