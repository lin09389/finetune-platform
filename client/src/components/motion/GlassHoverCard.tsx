import { HTMLMotionProps, motion } from 'framer-motion';
import React, { forwardRef } from 'react';
import { springs } from '../../theme/motion-tokens';
import { useMotionConfig } from './useMotionConfig';

export interface GlassHoverCardProps extends HTMLMotionProps<'div'> {
  /** 悬浮时是否有 3D 效果 */
  tilt3D?: boolean;
  /** 内容 */
  children: React.ReactNode;
}

/**
 * 具有玻璃拟态材质与高级悬浮动效的卡片组件
 */
export const GlassHoverCard = forwardRef<HTMLDivElement, GlassHoverCardProps>(
  ({ children, tilt3D = false, className = '', ...props }, ref) => {
    const { getSafeVariants, shouldReduceMotion } = useMotionConfig();

    // 默认悬浮变体：微微上浮并加强阴影
    const hoverVariants = {
      initial: { y: 0, scale: 1 },
      hover: { 
        y: -4, 
        scale: tilt3D ? 1.01 : 1,
        transition: springs.gentle 
      },
    };

    return (
      <motion.div
        ref={ref}
        variants={getSafeVariants(hoverVariants)}
        initial="initial"
        whileHover={shouldReduceMotion ? undefined : "hover"}
        className={`
          relative bg-bg-elevated backdrop-blur-glass border border-glass-border 
          rounded-xl shadow-glass overflow-hidden transition-shadow duration-300
          hover:shadow-[0_12px_32px_rgba(0,0,0,0.12)]
          ${className}
        `}
        style={{
          willChange: 'transform',
          transformStyle: 'preserve-3d', // 为可能的内部 3D 效果预留
          ...props.style,
        }}
        {...props}
      >
        {/* 玻璃拟态杂色层 - 增加质感 */}
        <div 
          className="absolute inset-0 pointer-events-none opacity-[0.03] mix-blend-overlay"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`
          }}
        />
        
        {/* 实际内容层 */}
        <div className="relative z-10">
          {children}
        </div>
      </motion.div>
    );
  }
);

GlassHoverCard.displayName = 'GlassHoverCard';
