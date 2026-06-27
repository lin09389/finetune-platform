import { useReducedMotion } from 'framer-motion';
import type { Variants } from 'framer-motion';
import { useMemo } from 'react';
import { transitions } from '../../theme/motion-tokens';

/**
 * 配置项：用于决定如何降级动效
 */
interface MotionConfigOptions {
  // 当开启减弱动态效果时，是否完全移除动画 (直接 render 最终态)
  removeOnReduce?: boolean;
}

/**
 * useMotionConfig: 
 * 用于根据系统的 prefers-reduced-motion 设置动态返回适合的 transition 或 variants。
 * 遵守可访问性 (a11y) 的要求。
 */
export function useMotionConfig({ removeOnReduce = false }: MotionConfigOptions = {}) {
  // framer-motion 提供的钩子，检测系统的减弱动态效果偏好
  const shouldReduceMotion = useReducedMotion();

  // 返回动态的持续时间修饰符
  const getDuration = (duration: number) => {
    if (shouldReduceMotion) return 0;
    return duration;
  };

  // 获得安全的过渡配置 (如果减弱动态效果，则瞬间完成，或者直接 opacity 硬切)
  const safeTransition = useMemo(() => {
    if (shouldReduceMotion) {
      return removeOnReduce
        ? { duration: 0 }
        : { duration: 0.01, ease: 'linear' };
    }
    return transitions.base;
  }, [shouldReduceMotion, removeOnReduce]);

  // 针对变体 (Variants) 进行安全处理
  const getSafeVariants = (variants: Variants): Variants => {
    if (!shouldReduceMotion) return variants;

    // 若减弱动态效果，只保留 opacity 变化，去掉位移(x,y)与缩放(scale)
    const reducedVariants: Variants = {};
    for (const key in variants) {
      if (variants[key]) {
        reducedVariants[key] = {
          ...variants[key],
          x: 0,
          y: 0,
          scale: 1,
          transition: { duration: removeOnReduce ? 0 : 0.01 },
        };
        // 如果原本有 opacity，则保留 opacity 变化
        if ('opacity' in variants[key]) {
          reducedVariants[key].opacity = variants[key].opacity;
        }
      }
    }
    return reducedVariants;
  };

  return {
    shouldReduceMotion,
    getDuration,
    safeTransition,
    getSafeVariants,
  };
}
