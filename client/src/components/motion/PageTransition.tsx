import { AnimatePresence, motion } from 'framer-motion';
import React from 'react';
import { pageVariants } from '../../theme/motion-tokens';
import { useMotionConfig } from './useMotionConfig';

interface PageTransitionProps {
  children: React.ReactNode;
  /**
   * 必须传入一个唯一的 key (通常为 router 的 location.pathname)，以触发 AnimatePresence
   */
  locationKey: string;
  /**
   * 自定义 className
   */
  className?: string;
  /**
   * 自定义外层 style
   */
  style?: React.CSSProperties;
}

/**
 * 页面切换包裹组件。基于 framer-motion 实现淡入淡出和微距位移的进出场动画。
 */
export const PageTransition: React.FC<PageTransitionProps> = ({
  children,
  locationKey,
  className,
  style,
}) => {
  const { getSafeVariants } = useMotionConfig();

  return (
    <AnimatePresence mode="wait" initial={true}>
      <motion.div
        key={locationKey}
        // 应用根据系统偏好处理后的安全变体
        variants={getSafeVariants(pageVariants)}
        initial="initial"
        animate="animate"
        exit="exit"
        className={className}
        style={{
          ...style,
          willChange: 'opacity, transform',
          transform: 'translateZ(0)', // 开启 GPU 硬件加速
        }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
};
