import { HTMLMotionProps, m, useMotionTemplate, useMotionValue, useTransform, useSpring, animate } from 'framer-motion';
import React, { forwardRef, MouseEvent, useRef } from 'react';
import { springs } from '../../theme/motion-tokens';
import { useMotionConfig } from './useMotionConfig';

export interface GlassHoverCardProps extends HTMLMotionProps<'div'> {
  /** 悬浮时是否有 3D 效果 */
  tilt3D?: boolean;
  /** 内容 */
  children: React.ReactNode;
}

/**
 * 具有玻璃拟态材质与高级 3D 视差悬浮动效的卡片组件 (带跟随光晕 Spotlight)
 */
export const GlassHoverCard = forwardRef<HTMLDivElement, GlassHoverCardProps>(
  ({ children, tilt3D = false, className = '', ...props }, ref) => {
    const { getSafeVariants, shouldReduceMotion } = useMotionConfig();
    const localRef = useRef<HTMLDivElement>(null);
    const resolvedRef = (ref as React.RefObject<HTMLDivElement>) || localRef;

    const mouseX = useMotionValue(0);
    const mouseY = useMotionValue(0);

    // 计算 3D 旋转角度 (基于鼠标在卡片中的绝对坐标相对于中心点的百分比)
    const rotateX = useTransform(mouseY, (y) => {
      if (!resolvedRef.current || !tilt3D) return 0;
      const height = resolvedRef.current.offsetHeight || 300;
      const maxRotation = 6; // 限制最大旋转 6 度，避免过于夸张
      return -((y - height / 2) / (height / 2)) * maxRotation;
    });

    const rotateY = useTransform(mouseX, (x) => {
      if (!resolvedRef.current || !tilt3D) return 0;
      const width = resolvedRef.current.offsetWidth || 300;
      const maxRotation = 6;
      return ((x - width / 2) / (width / 2)) * maxRotation;
    });

    // 物理平滑弹簧，消除微小抖动，提供极佳的物理重量与阻尼反馈
    const springRotateX = useSpring(rotateX, springs.tilt);
    const springRotateY = useSpring(rotateY, springs.tilt);

    function handleMouseMove(e: MouseEvent<HTMLDivElement>) {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      // 停止归位动画，切入实时追踪
      mouseX.stop();
      mouseY.stop();
      
      mouseX.set(x);
      mouseY.set(y);
      
      if (props.onMouseMove) props.onMouseMove(e);
    }

    function handleMouseEnter(e: MouseEvent<HTMLDivElement>) {
      if (props.onMouseEnter) props.onMouseEnter(e);
    }

    function handleMouseLeave(e: MouseEvent<HTMLDivElement>) {
      if (resolvedRef.current) {
        const width = resolvedRef.current.offsetWidth || 300;
        const height = resolvedRef.current.offsetHeight || 300;
        // 鼠标离开时，以柔和物理阻尼顺滑将卡片和光圈归位至中心点
        animate(mouseX, width / 2, springs.gentle);
        animate(mouseY, height / 2, springs.gentle);
      }
      if (props.onMouseLeave) props.onMouseLeave(e);
    }

    // 默认悬浮变体：克制的微上浮
    const hoverVariants = {
      initial: { y: 0, scale: 1 },
      hover: { 
        y: -2, 
        scale: 1.005,
        transition: springs.gentle 
      },
    };

    return (
      <m.div
        ref={resolvedRef}
        variants={getSafeVariants(hoverVariants)}
        initial="initial"
        whileHover={shouldReduceMotion ? undefined : "hover"}
        onMouseMove={handleMouseMove}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className={`
          relative border border-surface-border
          rounded-xl shadow-sm overflow-hidden transition-shadow duration-200
          hover:shadow-md
          group
          ${className}
        `}
        style={{
          background: 'var(--bg-secondary)',
          willChange: 'transform',
          transformStyle: 'preserve-3d',
          perspective: 1000,
          rotateX: shouldReduceMotion ? 0 : springRotateX,
          rotateY: shouldReduceMotion ? 0 : springRotateY,
          ...props.style,
        }}
        {...props}
      >
        {/* 跟随光晕 Spotlight 层 - 具有微深度层级产生视差 */}
        {!shouldReduceMotion && (
          <m.div
            className="pointer-events-none absolute -inset-px rounded-xl opacity-0 transition duration-300 group-hover:opacity-100"
            style={{
              transform: 'translateZ(10px)',
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
        
        {/* 发光边框层 - 具有稍高深度层级产生精美微光边缘 */}
        {!shouldReduceMotion && (
          <m.div
            className="pointer-events-none absolute -inset-px rounded-xl opacity-0 transition duration-300 group-hover:opacity-100 z-10"
            style={{
              transform: 'translateZ(15px)',
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

        {/* 实际内容层 */}
        <div 
          className="relative z-20 h-full"
        >
          {children}
        </div>
      </m.div>
    );
  }
);

GlassHoverCard.displayName = 'GlassHoverCard';
