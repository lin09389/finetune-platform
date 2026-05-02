import { HTMLMotionProps, motion, useMotionTemplate, useMotionValue, useReducedMotion } from 'framer-motion';
import React, { MouseEvent } from 'react';
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
  const reduceMotion = useReducedMotion();
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  function handleMouseMove({ currentTarget, clientX, clientY }: MouseEvent) {
    if (noHover) return;
    const { left, top } = currentTarget.getBoundingClientRect();
    mouseX.set(clientX - left);
    mouseY.set(clientY - top);
  }

  return (
    <motion.div
      className={`${styles.glassCard} ${intensityClass} ${className} group`}
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={
        !noHover && !reduceMotion
          ? { y: -4, transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] } }
          : undefined
      }
      transition={reduceMotion ? { duration: 0 } : { duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      onMouseMove={handleMouseMove}
      {...props}
    >
      {!noHover && !reduceMotion && (
        <>
          <motion.div
            className={`${styles.spotlight} transition-opacity duration-300 opacity-0 group-hover:opacity-100`}
            style={{
              background: useMotionTemplate`
                radial-gradient(
                  600px circle at ${mouseX}px ${mouseY}px,
                  var(--spotlight-color),
                  transparent 80%
                )
              `,
            }}
          />
          <motion.div
            className={`${styles.spotlightBorder} transition-opacity duration-300 opacity-0 group-hover:opacity-100`}
            style={{
              background: useMotionTemplate`
                radial-gradient(
                  400px circle at ${mouseX}px ${mouseY}px,
                  var(--spotlight-border),
                  transparent 50%
                )
              `,
            }}
          />
        </>
      )}
      <div className={styles.reflection} />
      <div className={styles.content}>{children}</div>
    </motion.div>
  );
};

export default GlassCard;
