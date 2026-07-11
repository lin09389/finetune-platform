import { m } from 'framer-motion';
import React, { useEffect, useRef, useState } from 'react';
import { buttonVariants, staggerContainer, staggerItem, transitions } from '../../theme/motion-tokens';
import { useMotionConfig } from '../motion/useMotionConfig';

// ====================================================
// MotionList — stagger 容器
// ====================================================
interface MotionListProps {
  children: React.ReactNode;
  stagger?: number;
  className?: string;
  style?: React.CSSProperties;
  layout?: boolean | "position" | "size";
}

export function MotionList({ children, stagger: _stagger, className, style, layout }: MotionListProps) {
  const { shouldReduceMotion, getSafeVariants } = useMotionConfig();
  if (shouldReduceMotion)
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  return (
    <m.div
      layout={layout}
      className={className}
      style={style}
      variants={getSafeVariants(staggerContainer)}
      initial="initial"
      animate="animate"
    >
      {children}
    </m.div>
  );
}

// ====================================================
// MotionItem — 淡入子项
// ====================================================
type MotionVariant = 'up' | 'scale' | 'left';

interface MotionItemProps {
  children: React.ReactNode;
  variant?: MotionVariant;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  layout?: boolean | "position" | "size";
  layoutId?: string;
}

const variantMap = {
  up: staggerItem,
  scale: { ...staggerItem, initial: { opacity: 0, scale: 0.98 } },
  left: { ...staggerItem, initial: { opacity: 0, x: -6 } },
};

export function MotionItem({
  children,
  variant = 'up',
  className,
  style,
  onClick,
  layout,
  layoutId,
}: MotionItemProps) {
  const { shouldReduceMotion, getSafeVariants } = useMotionConfig();
  if (shouldReduceMotion)
    return (
      <div className={className} style={style} onClick={onClick}>
        {children}
      </div>
    );
  return (
    <m.div
      layout={layout}
      layoutId={layoutId}
      className={className}
      style={style}
      variants={getSafeVariants(variantMap[variant])}
      onClick={onClick}
      whileHover={onClick ? { scale: 1.01, y: -1 } : undefined}
      whileTap={onClick ? { scale: 0.99, y: 0 } : undefined}
      exit={{ opacity: 0, y: -6, transition: transitions.fast }}
    >
      {children}
    </m.div>
  );
}

// ====================================================
// MotionCard — 带 hover 上浮的卡片
// ====================================================
interface MotionCardProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  lift?: boolean; // 是否启用 hover 上浮
  layout?: boolean | "position" | "size";
  layoutId?: string;
}

export function MotionCard({ children, className, style, onClick, lift = false, layout, layoutId }: MotionCardProps) {
  const { shouldReduceMotion, getSafeVariants } = useMotionConfig();
  if (shouldReduceMotion)
    return (
      <div className={className} style={style} onClick={onClick}>
        {children}
      </div>
    );
  return (
    <m.div
      layout={layout}
      layoutId={layoutId}
      className={className}
      style={style}
      variants={getSafeVariants(staggerItem)}
      onClick={onClick}
      whileHover={
        lift ? { boxShadow: 'var(--shadow-md)' } : { borderColor: 'var(--border-hover)' }
      }
      whileTap={onClick ? { scale: 0.99, y: 0 } : undefined}
      transition={transitions.fast}
    >
      {children}
    </m.div>
  );
}

// ====================================================
// CountUp — 数字从 0 滚动到目标值
// ====================================================
interface CountUpProps {
  value: number;
  decimals?: number;
  suffix?: string;
  prefix?: string;
  duration?: number;
  className?: string;
  style?: React.CSSProperties;
}

export function CountUp({
  value,
  decimals = 0,
  suffix = '',
  prefix = '',
  duration = 1.2,
  className,
  style,
}: CountUpProps) {
  const [display, setDisplay] = useState(0);
  const displayRef = useRef(0);
  const frameRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  const startValRef = useRef(0);
  const { shouldReduceMotion } = useMotionConfig();

  useEffect(() => {
    displayRef.current = display;
  }, [display]);

  useEffect(() => {
    if (shouldReduceMotion) {
      setDisplay(value);
      return;
    }
    startValRef.current = displayRef.current;
    startRef.current = null;

    const animateNum = (ts: number) => {
      if (startRef.current === null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const progress = Math.min(elapsed / (duration * 1000), 1);
      // ease out quart
      const eased = 1 - Math.pow(1 - progress, 4);
      setDisplay(startValRef.current + (value - startValRef.current) * eased);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animateNum);
      } else {
        setDisplay(value);
      }
    };

    frameRef.current = requestAnimationFrame(animateNum);
    return () => cancelAnimationFrame(frameRef.current);
  }, [duration, shouldReduceMotion, value]);

  const formatted = display.toFixed(decimals);
  const combinedClassName = `${className || ''} tabular-nums`.trim();
  return (
    <span className={combinedClassName} style={style}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}

// ====================================================
// FadeInSection — 滚动进入视口时淡入（无需 stagger 容器）
// ====================================================
interface FadeInSectionProps {
  children: React.ReactNode;
  delay?: number;
  className?: string;
  style?: React.CSSProperties;
  layout?: boolean | "position" | "size";
  layoutId?: string;
}

export function FadeInSection({ children, delay = 0, className, style, layout, layoutId }: FadeInSectionProps) {
  const { shouldReduceMotion } = useMotionConfig();
  if (shouldReduceMotion)
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  return (
    <m.div
      layout={layout}
      layoutId={layoutId}
      className={className}
      style={style}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...transitions.base, delay }}
    >
      {children}
    </m.div>
  );
}

// ====================================================
// MotionButton — 带 press 微反馈的按钮包装
// ====================================================
interface MotionButtonProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  disabled?: boolean;
}

export function MotionButton({ children, className, style, onClick, disabled }: MotionButtonProps) {
  const { shouldReduceMotion } = useMotionConfig();
  if (shouldReduceMotion || disabled)
    return (
      <div className={className} style={style} onClick={!disabled ? onClick : undefined}>
        {children}
      </div>
    );
  return (
    <m.div
      className={className}
      style={style}
      onClick={onClick}
      whileHover="hover"
      whileTap="tap"
      variants={buttonVariants}
    >
      {children}
    </m.div>
  );
}
