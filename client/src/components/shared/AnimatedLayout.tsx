import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import React from 'react';

interface AnimatedLayoutProps {
  children: React.ReactNode;
  animationKey?: string;
}

const pageVariants = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -16 },
};

const pageTransition = {
  duration: 0.3,
  ease: [0.23, 1, 0.32, 1] as [number, number, number, number],
};

const AnimatedLayout: React.FC<AnimatedLayoutProps> = ({ children, animationKey }) => {
  const reduceMotion = useReducedMotion();

  if (reduceMotion) {
    return <div style={{ width: '100%', height: '100%' }}>{children}</div>;
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={animationKey}
        initial="initial"
        animate="animate"
        exit="exit"
        variants={pageVariants}
        transition={pageTransition}
        style={{
          width: '100%',
          height: '100%',
          willChange: 'transform, opacity',
          maxWidth: '1600px', // Phase 2: Add max-width constraint for ultrawide screens
          margin: '0 auto', // Center content
        }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
};

export default AnimatedLayout;
