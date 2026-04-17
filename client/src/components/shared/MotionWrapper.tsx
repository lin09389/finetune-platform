import { motion } from 'framer-motion';
import React, { useEffect, useRef, useState } from 'react';
import {
  containerVariants,
  itemFromLeft,
  itemVariants,
  scaleItem,
  useMotion,
} from '../../hooks/useMotion';

// ====================================================
// MotionList — stagger 容器
// ====================================================
interface MotionListProps {
  children: React.ReactNode;
  stagger?: number;
  className?: string;
  style?: React.CSSProperties;
}

export function MotionList({ children, stagger = 0.07, className, style }: MotionListProps) {
  const { skip } = useMotion();
  if (skip)
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  return (
    <motion.div
      className={className}
      style={style}
      variants={containerVariants(stagger)}
      initial="hidden"
      animate="show"
    >
      {children}
    </motion.div>
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
}

const variantMap = {
  up: itemVariants,
  scale: scaleItem,
  left: itemFromLeft,
};

export function MotionItem({
  children,
  variant = 'up',
  className,
  style,
  onClick,
}: MotionItemProps) {
  const { skip } = useMotion();
  if (skip)
    return (
      <div className={className} style={style} onClick={onClick}>
        {children}
      </div>
    );
  return (
    <motion.div
      className={className}
      style={style}
      variants={variantMap[variant]}
      onClick={onClick}
      whileHover={onClick ? { scale: 1.01 } : undefined}
      whileTap={onClick ? { scale: 0.99 } : undefined}
    >
      {children}
    </motion.div>
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
}

export function MotionCard({ children, className, style, onClick, lift = false }: MotionCardProps) {
  const { skip } = useMotion();
  if (skip)
    return (
      <div className={className} style={style} onClick={onClick}>
        {children}
      </div>
    );
  return (
    <motion.div
      className={className}
      style={style}
      variants={itemVariants}
      onClick={onClick}
      whileHover={
        lift ? { y: -3, boxShadow: 'var(--shadow-lg)' } : { borderColor: 'var(--border-hover)' }
      }
      whileTap={onClick ? { scale: 0.99 } : undefined}
      transition={{ duration: 0.15 }}
    >
      {children}
    </motion.div>
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
  const frameRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);
  const startValRef = useRef(0);
  const { skip } = useMotion();

  useEffect(() => {
    if (skip) {
      setDisplay(value);
      return;
    }
    startValRef.current = display;
    startRef.current = null;

    const animate = (ts: number) => {
      if (startRef.current === null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const progress = Math.min(elapsed / (duration * 1000), 1);
      // ease out quart
      const eased = 1 - Math.pow(1 - progress, 4);
      setDisplay(startValRef.current + (value - startValRef.current) * eased);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate);
      } else {
        setDisplay(value);
      }
    };

    frameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameRef.current);
  }, [value]);

  const formatted = display.toFixed(decimals);
  return (
    <span className={className} style={style}>
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
}

export function FadeInSection({ children, delay = 0, className, style }: FadeInSectionProps) {
  const { skip } = useMotion();
  if (skip)
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  return (
    <motion.div
      className={className}
      style={style}
      initial={{ opacity: 0, y: 16, filter: 'blur(4px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ delay, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
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
  const { skip } = useMotion();
  if (skip || disabled)
    return (
      <div className={className} style={style} onClick={!disabled ? onClick : undefined}>
        {children}
      </div>
    );
  return (
    <motion.div
      className={className}
      style={style}
      onClick={onClick}
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.96 }}
      transition={{ type: 'spring', stiffness: 400, damping: 20 }}
    >
      {children}
    </motion.div>
  );
}
