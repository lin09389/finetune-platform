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
          boxShadow: `0 0 50px ${glowColor}`,
          opacity: 0.15,
          zIndex: 0,
        }}
      />
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ position: 'absolute', transform: `rotate(${rotation}deg)`, zIndex: 1 }}
      >
        {/* Background Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${dashFillLength} ${dashGap}`}
          strokeDashoffset={0}
          opacity={0.15}
        />
        {/* Animated Fill Track */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: emptyOffset }}
          animate={{ strokeDashoffset: targetOffset }}
          transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
          style={{
            filter: `drop-shadow(0 0 6px ${color})`
          }}
        />
      </svg>
      <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {children}
      </div>
    </div>
  );
}
