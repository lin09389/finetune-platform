import { motion } from 'framer-motion';

interface LoadingSpinnerProps {
  size?: 'small' | 'medium' | 'large';
  text?: string;
  fullScreen?: boolean;
}

const sizeMap = {
  small: { spinner: 16, border: 2 },
  medium: { spinner: 24, border: 2 },
  large: { spinner: 32, border: 3 },
};

export default function LoadingSpinner({
  size = 'medium',
  text,
  fullScreen = false,
}: LoadingSpinnerProps) {
  const { spinner, border } = sizeMap[size];

  const spinnerContent = (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
      }}
    >
      <motion.div
        animate={{ rotate: 360 }}
        transition={{
          duration: 1,
          repeat: Infinity,
          ease: 'linear',
        }}
        style={{
          width: spinner,
          height: spinner,
          border: `${border}px solid var(--border-color)`,
          borderTopColor: 'var(--accent-primary)',
          borderRadius: '50%',
        }}
      />
      {text && (
        <span
          style={{
            fontSize: size === 'small' ? '12px' : '14px',
            color: 'var(--text-secondary)',
            fontWeight: 500,
          }}
        >
          {text}
        </span>
      )}
    </div>
  );

  if (fullScreen) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          background: 'var(--bg-primary)',
        }}
      >
        {spinnerContent}
      </div>
    );
  }

  return spinnerContent;
}

// 点状加载动画
export function LoadingDots({ size = 'medium' }: { size?: 'small' | 'medium' | 'large' }) {
  const dotSize = size === 'small' ? 6 : size === 'medium' ? 8 : 10;

  return (
    <div
      style={{
        display: 'flex',
        gap: 4,
        alignItems: 'center',
      }}
    >
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.5, 1, 0.5],
          }}
          transition={{
            duration: 1,
            repeat: Infinity,
            delay: i * 0.15,
            ease: 'easeInOut',
          }}
          style={{
            width: dotSize,
            height: dotSize,
            borderRadius: '50%',
            background: 'var(--accent-primary)',
          }}
        />
      ))}
    </div>
  );
}

// 脉冲加载动画
export function LoadingPulse({ size = 'medium' }: { size?: 'small' | 'medium' | 'large' }) {
  const pulseSize = size === 'small' ? 32 : size === 'medium' ? 48 : 64;

  return (
    <div
      style={{
        position: 'relative',
        width: pulseSize,
        height: pulseSize,
      }}
    >
      <motion.div
        animate={{
          scale: [1, 1.2, 1],
          opacity: [0.5, 0.8, 0.5],
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          background: 'var(--accent-primary)',
        }}
      />
      <motion.div
        animate={{
          scale: [1.2, 1, 1.2],
          opacity: [0.3, 0.6, 0.3],
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: 'easeInOut',
          delay: 0.5,
        }}
        style={{
          position: 'absolute',
          inset: -8,
          borderRadius: '50%',
          background: 'var(--accent-primary)',
        }}
      />
    </div>
  );
}

// 骨架屏加载
export function SkeletonLoader({
  lines = 3,
  width = '100%',
}: {
  lines?: number;
  width?: string | number;
}) {
  return (
    <div style={{ width, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.5 }}
          animate={{ opacity: [0.5, 0.8, 0.5] }}
          transition={{
            duration: 1.5,
            repeat: Infinity,
            delay: i * 0.1,
            ease: 'easeInOut',
          }}
          style={{
            height: i === 0 ? 20 : 14,
            width: i === lines - 1 ? '60%' : '100%',
            background: 'var(--bg-elevated)',
            borderRadius: '4px',
          }}
        />
      ))}
    </div>
  );
}
