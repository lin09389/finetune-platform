import { motion } from 'framer-motion';
import React from 'react';

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
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const gapRatio = gapDegree / 360;
  const dashGap = circumference * gapRatio;
  const dashFillLength = circumference - dashGap;

  const safePercent = Math.min(100, Math.max(0, percent));
  const rotation = 90 + (gapDegree / 2);

  const emptyOffset = circumference;
  const targetOffset = circumference - (safePercent / 100) * dashFillLength;

  const gradientId = `gradient-${Math.random().toString(36).substr(2, 9)}`;
  const glowFilterId = `glow-${Math.random().toString(36).substr(2, 9)}`;

  return (
    <div style={{ position: 'relative', width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {/* Background Glow Overlay */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: size - strokeWidth * 2,
          height: size - strokeWidth * 2,
          borderRadius: '50%',
          boxShadow: `0 0 50px ${glowColor}, inset 0 0 20px ${glowColor}`,
          opacity: 0.25,
          zIndex: 0,
        }}
      />
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
          <filter id={glowFilterId} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background Track - non gray, subtle tech outline */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255, 255, 255, 0.04)"
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
          initial={{ strokeDashoffset: emptyOffset }}
          animate={{ strokeDashoffset: targetOffset }}
          transition={{ duration: 1.5, ease: [0.23, 1, 0.32, 1] }}
          filter={`url(#${glowFilterId})`}
        />
      </svg>
      <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {children}
      </div>
    </div>
  );
}
