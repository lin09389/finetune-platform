import React from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';

interface AnimatedLayoutProps {
  children: React.ReactNode;
  animationKey?: string;
}

const pageVariants = {
  initial: { opacity: 0, y: 12, filter: 'blur(4px)' },
  animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
  exit: { opacity: 0, y: -12, filter: 'blur(4px)' },
};

const pageTransition = {
  duration: 0.4,
  ease: [0.16, 1, 0.3, 1] as [number, number, number, number],
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
        style={{ width: '100%', height: '100%' }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
};

export default AnimatedLayout;
