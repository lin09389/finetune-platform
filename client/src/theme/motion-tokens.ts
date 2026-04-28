import { Transition, Variants } from 'framer-motion';

/**
 * 动效时长字典 (毫秒转化为秒，Framer Motion 使用秒)
 */
export const duration = {
  instant: 0.1,
  fast: 0.15,
  base: 0.2,
  smooth: 0.3,
  slow: 0.5,
};

/**
 * 缓动曲线字典
 */
export const easings = {
  // 优雅的缓出 (减速)，适合进入动画
  smoothOut: [0.16, 1, 0.3, 1] as [number, number, number, number],
  // 缓入 (加速)，适合退出动画
  smoothIn: [0.55, 0, 1, 0.45] as [number, number, number, number],
  // 标准缓入缓出
  easeInOut: [0.65, 0, 0.35, 1] as [number, number, number, number],
};

/**
 * 物理弹簧配置
 */
export const springs = {
  // 柔和无回弹
  gentle: { type: 'spring' as const, stiffness: 200, damping: 25 },
  // 标准物理感
  base: { type: 'spring' as const, stiffness: 400, damping: 30 },
  // Q弹活泼
  bouncy: { type: 'spring' as const, stiffness: 500, damping: 20 },
  // 强力按压反馈
  tap: { type: 'spring' as const, stiffness: 400, damping: 17 },
};

/**
 * 全局预设过渡对象
 */
export const transitions = {
  instant: { duration: duration.instant, ease: 'linear' } as Transition,
  fast: { duration: duration.fast, ease: easings.smoothOut } as Transition,
  base: { duration: duration.base, ease: easings.smoothOut } as Transition,
  smooth: { duration: duration.smooth, ease: easings.smoothOut } as Transition,
  slow: { duration: duration.slow, ease: easings.smoothOut } as Transition,
  springBase: springs.base as Transition,
  springGentle: springs.gentle as Transition,
  springBouncy: springs.bouncy as Transition,
};

/**
 * 通用变体预设 (Variants)
 */
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: transitions.smooth },
  exit: { opacity: 0, y: -10, transition: transitions.fast },
};

export const buttonVariants: Variants = {
  initial: { scale: 1 },
  hover: { scale: 1.02, transition: springs.base },
  tap: { scale: 0.96, transition: springs.tap },
};

export const fadeVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: transitions.base },
  exit: { opacity: 0, transition: transitions.fast },
};

/**
 * 交错子元素动画
 */
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
  animate: { opacity: 1, y: 0, transition: transitions.base },
};
