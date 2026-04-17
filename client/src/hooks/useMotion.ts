import { useReducedMotion } from 'framer-motion';

// ====================================================
// 统一动画配置 — 供全部页面使用
// ====================================================

export const SPRING = { type: 'spring' as const, stiffness: 400, damping: 28 };
export const EASE_OUT = [0.16, 1, 0.3, 1] as const;

/** 容器：stagger 子项入场 */
export const containerVariants = (stagger = 0.07) => ({
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: stagger },
  },
});

/** 子项：向上淡入 + 轻微模糊 */
export const itemVariants = {
  hidden: { opacity: 0, y: 14, filter: 'blur(4px)' },
  show: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: 0.38, ease: EASE_OUT },
  },
};

/** 子项：向右淡入 */
export const itemFromLeft = {
  hidden: { opacity: 0, x: -12 },
  show: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.35, ease: EASE_OUT },
  },
};

/** 子项：缩放淡入 */
export const scaleItem = {
  hidden: { opacity: 0, scale: 0.95 },
  show: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.32, ease: EASE_OUT },
  },
};

/** 表格行：逐行淡入 */
export const rowVariants = (i: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.04, duration: 0.3, ease: EASE_OUT },
  },
});

/** 数字计数动画配置 */
export const countTransition = { duration: 1.2, ease: [0.16, 1, 0.3, 1] as const };

/**
 * useMotion — 返回是否应跳过动画（prefers-reduced-motion）
 * 用法：
 *   const { skip, container, item } = useMotion()
 *   if (skip) return <div>{children}</div>
 *   return <motion.div variants={container} initial="hidden" animate="show">...</motion.div>
 */
export function useMotion(stagger = 0.07) {
  const reduce = useReducedMotion();
  return {
    skip: reduce,
    container: containerVariants(stagger),
    item: itemVariants,
    scaleItem,
    fromLeft: itemFromLeft,
  };
}
