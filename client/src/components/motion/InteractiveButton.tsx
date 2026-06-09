import { AnimatePresence, HTMLMotionProps, motion } from 'framer-motion';
import React, { forwardRef, useState } from 'react';
import { buttonVariants, springs } from '../../theme/motion-tokens';
import { useMotionConfig } from './useMotionConfig';

export interface InteractiveButtonProps extends Omit<HTMLMotionProps<'button'>, 'onClick'> {
  /** 按钮点击事件 */
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  /** 是否开启水波纹反馈 */
  ripple?: boolean;
  /** 按钮文字或子节点 */
  children: React.ReactNode;
  /** 按钮变体类型 */
  variant?: 'primary' | 'secondary' | 'glass' | 'ghost';
  /** 是否禁用 */
  disabled?: boolean;
  /** 是否启用磁吸效果 */
  magnetic?: boolean;
}

/**
 * 带有物理弹簧反馈和可选水波纹的交互式按钮
 */
export const InteractiveButton = forwardRef<HTMLButtonElement, InteractiveButtonProps>(
  (
    {
      children,
      onClick,
      ripple = true,
      variant = 'primary',
      disabled = false,
      magnetic = false,
      className = '',
      ...props
    },
    ref,
  ) => {
    const { getSafeVariants, shouldReduceMotion } = useMotionConfig();
    const [ripples, setRipples] = useState<{ x: number; y: number; id: number }[]>([]);

    // Magnetic effect state
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const buttonRef = React.useRef<HTMLButtonElement | null>(null);

    // Merge refs
    const mergedRef = (node: HTMLButtonElement) => {
      buttonRef.current = node;
      if (typeof ref === 'function') ref(node);
      else if (ref) (ref as React.MutableRefObject<HTMLButtonElement | null>).current = node;
    };

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      if (disabled) return;

      if (ripple && !shouldReduceMotion) {
        const rect = e.currentTarget.getBoundingClientRect();
        const newRipple = {
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
          id: Date.now(),
        };
        setRipples((prev) => [...prev, newRipple]);

        // 自动清除涟漪元素，避免内存泄漏
        setTimeout(() => {
          setRipples((prev) => prev.filter((r) => r.id !== newRipple.id));
        }, 600);
      }

      onClick?.(e);
    };

    const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
      if (!magnetic || disabled || shouldReduceMotion || !buttonRef.current) return;
      const { clientX, clientY } = e;
      const { left, top, width, height } = buttonRef.current.getBoundingClientRect();
      const x = (clientX - (left + width / 2)) * 0.2;
      const y = (clientY - (top + height / 2)) * 0.2;
      setPosition({ x, y });
    };

    const handleMouseLeave = () => {
      if (magnetic) {
        setPosition({ x: 0, y: 0 });
      }
    };

    // 变体样式映射
    const variantStyles: Record<string, string> = {
      primary: 'bg-accent-primary text-white hover:bg-accent-secondary shadow-md',
      secondary: 'bg-bg-secondary text-text-primary hover:bg-bg-hover border border-glass-border',
      glass:
        'bg-bg-elevated backdrop-blur-glass text-text-primary border border-glass-border shadow-glass hover:bg-bg-hover',
      ghost: 'bg-transparent text-text-secondary hover:bg-bg-hover hover:text-text-primary',
    };

    const baseClasses =
      'relative overflow-hidden inline-flex items-center justify-center px-4 py-2 rounded-lg font-medium transition-colors outline-none focus:ring-2 focus:ring-accent-primary/50 focus:ring-offset-1 focus:ring-offset-bg-primary';
    const disabledClasses = 'opacity-50 cursor-not-allowed';

    return (
      <motion.button
        ref={mergedRef}
        disabled={disabled}
        onClick={handleClick}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        animate={magnetic ? { x: position.x, y: position.y } : undefined}
        variants={getSafeVariants(buttonVariants)}
        initial="initial"
        whileHover={!disabled ? 'hover' : undefined}
        whileTap={!disabled ? 'tap' : undefined}
        transition={magnetic ? springs.magnetic : undefined}
        className={`${baseClasses} ${variantStyles[variant]} ${
          disabled ? disabledClasses : ''
        } ${className}`}
        style={{
          willChange: 'transform',
          ...props.style,
        }}
        {...props}
      >
        <span className="relative z-10 flex items-center justify-center">{children}</span>

        {/* 水波纹容器 */}
        <AnimatePresence>
          {ripples.map((r) => (
            <motion.span
              key={r.id}
              initial={{ scale: 0, opacity: 0.4 }}
              animate={{ scale: 4, opacity: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
              className="absolute bg-white/30 rounded-full pointer-events-none"
              style={{
                left: r.x,
                top: r.y,
                width: '100px',
                height: '100px',
                marginTop: '-50px',
                marginLeft: '-50px',
              }}
            />
          ))}
        </AnimatePresence>
      </motion.button>
    );
  },
);

InteractiveButton.displayName = 'InteractiveButton';
