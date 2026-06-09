import { Transition, Variants } from 'framer-motion';

export const transitions = {
  fast: { duration: 0.14, ease: [0.23, 1, 0.32, 1] } as Transition,
  base: { duration: 0.22, ease: [0.23, 1, 0.32, 1] } as Transition,
  slow: { duration: 0.34, ease: [0.23, 1, 0.32, 1] } as Transition,
  slower: { duration: 0.52, ease: [0.23, 1, 0.32, 1] } as Transition,
  spring: { type: 'spring', stiffness: 320, damping: 28 } as Transition,
  springGentle: { type: 'spring', stiffness: 220, damping: 26 } as Transition,
  springBouncy: { type: 'spring', stiffness: 460, damping: 22 } as Transition,
};

export const messageVariants: Variants = {
  initial: {
    opacity: 0,
  },
  animate: {
    opacity: 1,
    transition: { duration: 0.15, ease: [0.23, 1, 0.32, 1] },
  },
  exit: {
    opacity: 0,
    transition: { duration: 0.1 },
  },
};

export const buttonVariants: Variants = {
  initial: { scale: 1 },
  hover: {
    scale: 1.02,
    transition: transitions.fast,
  },
  tap: {
    scale: 0.98,
    transition: transitions.fast,
  },
};

export const cardVariants: Variants = {
  initial: {
    opacity: 0,
    y: 10,
  },
  animate: {
    opacity: 1,
    y: 0,
    transition: transitions.base,
  },
  hover: {
    y: -2,
    boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12)',
    transition: transitions.fast,
  },
};

export const fadeVariants: Variants = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: transitions.base,
  },
  exit: {
    opacity: 0,
    transition: transitions.fast,
  },
};

export const slideVariants: Variants = {
  initial: { opacity: 0, x: -20 },
  animate: {
    opacity: 1,
    x: 0,
    transition: transitions.slow,
  },
  exit: {
    opacity: 0,
    x: 20,
    transition: transitions.fast,
  },
};

export const scaleVariants: Variants = {
  initial: { opacity: 0, scale: 0.9 },
  animate: {
    opacity: 1,
    scale: 1,
    transition: transitions.spring,
  },
  exit: {
    opacity: 0,
    scale: 0.9,
    transition: transitions.fast,
  },
};

export const staggerContainer: Variants = {
  initial: {},
  animate: {
    transition: {
      staggerChildren: 0.05,
      delayChildren: 0.1,
    },
  },
};

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: {
    opacity: 1,
    y: 0,
    transition: transitions.base,
  },
};

export const loadingDotsVariants: Variants = {
  initial: { opacity: 0.45 },
  animate: {
    opacity: [0.45, 1, 0.45],
    transition: {
      duration: 1.1,
      repeat: Infinity,
      ease: 'easeInOut',
    },
  },
};

export const pulseVariants: Variants = {
  initial: { scale: 1, opacity: 1 },
  animate: {
    scale: [1, 1.025, 1],
    opacity: [1, 0.9, 1],
    transition: {
      duration: 2.6,
      repeat: Infinity,
      ease: 'easeInOut',
    },
  },
};

export const typingIndicatorVariants: Variants = {
  initial: { y: 0 },
  animate: {
    y: [-1, 1, -1],
    transition: {
      duration: 0.9,
      repeat: Infinity,
      ease: 'easeInOut',
    },
  },
};

export const shimmerVariants: Variants = {
  initial: { backgroundPosition: '-160% 0' },
  animate: {
    backgroundPosition: '160% 0',
    transition: {
      duration: 1.8,
      repeat: Infinity,
      ease: 'linear',
    },
  },
};

export const floatVariants: Variants = {
  initial: { y: 0 },
  animate: {
    y: [-5, 5, -5],
    transition: {
      duration: 3,
      repeat: Infinity,
      ease: 'easeInOut',
    },
  },
};

export const rotateVariants: Variants = {
  initial: { rotate: 0 },
  animate: {
    rotate: 360,
    transition: {
      duration: 1,
      repeat: Infinity,
      ease: 'linear',
    },
  },
};

export const bounceInVariants: Variants = {
  initial: { opacity: 0, scale: 0.3, y: 50 },
  animate: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: {
      type: 'spring',
      stiffness: 300,
      damping: 20,
    },
  },
  exit: {
    opacity: 0,
    scale: 0.3,
    y: 50,
    transition: transitions.fast,
  },
};

export const getStaggerDelay = (index: number, baseDelay: number = 0.05): number => {
  return index * baseDelay;
};

export const createStaggerVariants = (delay: number = 0.05): Variants => ({
  initial: { opacity: 0, y: 10 },
  animate: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      ...transitions.base,
      delay: i * delay,
    },
  }),
});
