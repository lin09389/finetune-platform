import { motion } from 'framer-motion';
import React, { useId } from 'react';
import { useMotionConfig } from './useMotionConfig';

export interface NeonProgressRingProps {
  percent: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  glowColor?: string;
  children?: React.ReactNode;
  gapDegree?: number;
}

export function NeonProgressRing({
  percent,
  size = 160,
  strokeWidth = 8,
  color = 'var(--accent-primary)',
  glowColor = 'var(--accent-primary-light)',
  children,
  gapDegree = 90
}: NeonProgressRingProps) {
  const { shouldReduceMotion } = useMotionConfig();
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const gapRatio = gapDegree / 360;
  const dashGap = circumference * gapRatio;
  const dashFillLength = circumference - dashGap;

  const safePercent = Math.min(100, Math.max(0, percent));
  const rotation = 90 + (gapDegree / 2);

  const targetOffset = circumference - (safePercent / 100) * dashFillLength;

  const instanceId = useId().replace(/:/g, '');
  const gradientId = `progress-${instanceId}`;

  return (
    <div style={{ position: 'relative', width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ position: 'absolute', transform: `rotate(${rotation}deg)`, zIndex: 1, overflow: 'visible' }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={color} />
            <stop offset="100%" stopColor={glowColor} stopOpacity={0.8} />
          </linearGradient>
        </defs>

        {/* Background Track - non gray, subtle tech outline */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border-subtle)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${dashFillLength} ${dashGap}`}
          strokeDashoffset={0}
        />

        {/* Inner subtle track for depth */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius - strokeWidth / 2}
          fill="none"
          stroke={glowColor}
          strokeWidth={1}
          opacity={0.15}
          strokeDasharray={`${dashFillLength} ${dashGap}`}
        />

        {/* Animated Fill Track */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={false}
          animate={{ strokeDashoffset: targetOffset }}
          transition={{ duration: shouldReduceMotion ? 0 : 0.35, ease: [0.23, 1, 0.32, 1] }}
        />
      </svg>
      <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {children}
      </div>
    </div>
  );
}
