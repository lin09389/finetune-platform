import { HTMLMotionProps, motion, useMotionTemplate, useMotionValue } from 'framer-motion';
import React, { forwardRef, MouseEvent } from 'react';
import { springs } from '../../theme/motion-tokens';
import { useMotionConfig } from './useMotionConfig';

export interface GlassHoverCardProps extends HTMLMotionProps<'div'> {
  /** 悬浮时是否有 3D 效果 */
  tilt3D?: boolean;
  /** 内容 */
  children: React.ReactNode;
}

/**
 * 具有玻璃拟态材质与高级悬浮动效的卡片组件 (带跟随光晕 Spotlight)
 */
export const GlassHoverCard = forwardRef<HTMLDivElement, GlassHoverCardProps>(
  ({ children, tilt3D = false, className = '', ...props }, ref) => {
    const { getSafeVariants, shouldReduceMotion } = useMotionConfig();
    const mouseX = useMotionValue(0);
    const mouseY = useMotionValue(0);

    function handleMouseMove({ currentTarget, clientX, clientY }: MouseEvent) {
      const { left, top } = currentTarget.getBoundingClientRect();
      mouseX.set(clientX - left);
      mouseY.set(clientY - top);
    }

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
        onMouseMove={handleMouseMove}
        className={`
          relative backdrop-blur-glass border border-glass-border 
          rounded-xl shadow-glass overflow-hidden transition-shadow duration-300
          hover:shadow-[0_12px_32px_rgba(0,0,0,0.12)]
          group
          ${className}
        `}
        style={{
          background: 'var(--glass-bg)',
          willChange: 'transform',
          transformStyle: 'preserve-3d',
          ...props.style,
        }}
        {...props}
      >
        {/* 跟随光晕 Spotlight 层 */}
        {!shouldReduceMotion && (
          <motion.div
            className="pointer-events-none absolute -inset-px rounded-xl opacity-0 transition duration-300 group-hover:opacity-100"
            style={{
              background: useMotionTemplate`
                radial-gradient(
                  650px circle at ${mouseX}px ${mouseY}px,
                  var(--spotlight-color),
                  transparent 80%
                )
              `,
            }}
          />
        )}
        
        {/* 发光边框层 */}
        {!shouldReduceMotion && (
          <motion.div
            className="pointer-events-none absolute -inset-px rounded-xl opacity-0 transition duration-300 group-hover:opacity-100 z-10"
            style={{
              background: useMotionTemplate`
                radial-gradient(
                  400px circle at ${mouseX}px ${mouseY}px,
                  var(--spotlight-border),
                  transparent 50%
                )
              `,
              WebkitMaskImage: `url("data:image/svg+xml,%3Csvg width='100%25' height='100%25' xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='100%25' height='100%25' fill='none' rx='12' ry='12' stroke='black' stroke-width='2'/%3E%3C/svg%3E")`,
              maskImage: `url("data:image/svg+xml,%3Csvg width='100%25' height='100%25' xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='100%25' height='100%25' fill='none' rx='12' ry='12' stroke='black' stroke-width='2'/%3E%3C/svg%3E")`,
            }}
          />
        )}

        {/* 玻璃拟态杂色层 - 增加质感 */}
        <div 
          className="absolute inset-0 pointer-events-none opacity-[0.03] mix-blend-overlay"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`
          }}
        />
        
        {/* 实际内容层 */}
        <div className="relative z-20 h-full">
          {children}
        </div>
      </motion.div>
    );
  }
);

GlassHoverCard.displayName = 'GlassHoverCard';
