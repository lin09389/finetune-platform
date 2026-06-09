import { Transition, Variants } from 'framer-motion';

/**
 * 动效时长字典 (毫秒转化为秒，Framer Motion 使用秒)
 */
export const duration = {
  instant: 0.1,
  fast: 0.12,
  base: 0.18,
  smooth: 0.25,
  slow: 0.4,
};

/**
 * 缓动曲线字典
 */
export const easings = {
  // 顶级丝滑指数衰减，极速响应+柔和收尾
  smoothOut: [0.23, 1, 0.32, 1] as [number, number, number, number],
  // 快速干脆的退出，不拖泥带水
  smoothIn: [0.75, 0, 0.25, 1] as [number, number, number, number],
  // Apple风格标准缓动
  easeInOut: [0.65, 0, 0.35, 1] as [number, number, number, number],
};

/**
 * 物理弹簧配置
 */
export const springs = {
  // 柔和无回弹，提升跟手感
  gentle: { type: 'spring' as const, stiffness: 250, damping: 28 },
  // 标准物理感，减弱抖动
  base: { type: 'spring' as const, stiffness: 350, damping: 35 },
  // 丝滑 Q弹，降低生硬弹跳
  bouncy: { type: 'spring' as const, stiffness: 450, damping: 22 },
  // 极具质感的按压反馈
  tap: { type: 'spring' as const, stiffness: 450, damping: 25 },
  // 3D 倾斜专用：极高阻尼，顺滑无回弹，模拟重物理惯性
  tilt: { type: 'spring' as const, stiffness: 120, damping: 25, mass: 1 },
  // 极速干脆但无残影抖动
  snappy: { type: 'spring' as const, stiffness: 600, damping: 35 },
  // 磁吸效果的反馈
  magnetic: { type: 'spring' as const, stiffness: 350, damping: 20, mass: 0.6 },
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
  springTilt: springs.tilt as Transition,
  springSnappy: springs.snappy as Transition,
  springMagnetic: springs.magnetic as Transition,
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
  hover: { scale: 1.02, y: -1, transition: springs.snappy },
  tap: { scale: 0.96, y: 0, transition: springs.tap },
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
