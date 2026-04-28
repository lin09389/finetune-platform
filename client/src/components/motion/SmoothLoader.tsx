import { motion } from 'framer-motion';
import React from 'react';
import { useMotionConfig } from './useMotionConfig';

export interface SmoothLoaderProps {
  /** 尺寸: sm(16px), md(24px), lg(32px) 或自定义像素值 */
  size?: 'sm' | 'md' | 'lg' | number;
  /** 颜色: 使用 tailwind 颜色值或 css 变量 */
  color?: string;
  /** 是否全屏遮罩加载 */
  fullscreen?: boolean;
}

/**
 * 丝滑 SVG 加载态，GPU 硬件加速，避免传统 css animation 的卡顿
 */
export const SmoothLoader: React.FC<SmoothLoaderProps> = ({ 
  size = 'md', 
  color = 'var(--accent-primary)',
  fullscreen = false 
}) => {
  const { shouldReduceMotion } = useMotionConfig();

  const sizeMap = {
    sm: 16,
    md: 24,
    lg: 32,
  };

  const actualSize = typeof size === 'number' ? size : sizeMap[size];

  const svgAnimation = {
    rotate: shouldReduceMotion ? 0 : 360,
  };

  const circleAnimation = {
    strokeDasharray: shouldReduceMotion ? ["100, 200"] : ["1, 200", "89, 200", "89, 200"],
    strokeDashoffset: shouldReduceMotion ? [0] : [0, -35, -124],
  };

  const loaderContent = (
    <motion.svg
      width={actualSize}
      height={actualSize}
      viewBox="25 25 50 50"
      animate={svgAnimation}
      transition={{ 
        duration: 2, 
        ease: "linear", 
        repeat: Infinity 
      }}
      className="inline-block transform-gpu"
    >
      <motion.circle
        cx="50"
        cy="50"
        r="20"
        fill="none"
        strokeWidth="4"
        stroke={color}
        strokeLinecap="round"
        animate={circleAnimation}
        transition={{ 
          duration: 1.5, 
          ease: "easeInOut", 
          repeat: Infinity 
        }}
      />
    </motion.svg>
  );

  if (fullscreen) {
    return (
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-modal flex items-center justify-center bg-bg-overlay backdrop-blur-sm"
      >
        {loaderContent}
      </motion.div>
    );
  }

  return loaderContent;
};
