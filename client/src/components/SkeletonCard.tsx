import { Card } from 'antd';
import { motion } from 'framer-motion';

interface SkeletonCardProps {
  rows?: number;
  avatar?: boolean;
  actions?: boolean;
  style?: React.CSSProperties;
}

export default function SkeletonCard({
  rows = 3,
  avatar = true,
  actions = false,
  style,
}: SkeletonCardProps) {
  return (
    <Card
      style={{
        borderRadius: '8px',
        border: '1px solid var(--border-color)',
        ...style,
      }}
      styles={{ body: { padding: '20px' } }}
    >
      <div style={{ display: 'flex', gap: 16 }}>
        {avatar && (
          <motion.div
            initial={{ opacity: 0.5 }}
            animate={{ opacity: [0.5, 0.8, 0.5] }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
            style={{
              width: 44,
              height: 44,
              borderRadius: '8px',
              background: 'var(--bg-elevated)',
              flexShrink: 0,
            }}
          />
        )}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {Array.from({ length: rows }).map((_, i) => (
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
                width: i === 0 ? '40%' : i === rows - 1 ? '60%' : '100%',
                background: 'var(--bg-elevated)',
                borderRadius: '4px',
              }}
            />
          ))}
        </div>
      </div>

      {actions && (
        <div
          style={{
            marginTop: 16,
            paddingTop: 16,
            borderTop: '1px solid var(--border-color)',
            display: 'flex',
            gap: 8,
            justifyContent: 'flex-end',
          }}
        >
          {Array.from({ length: 2 }).map((_, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0.5 }}
              animate={{ opacity: [0.5, 0.8, 0.5] }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                delay: 0.3 + i * 0.1,
                ease: 'easeInOut',
              }}
              style={{
                width: 80,
                height: 32,
                background: 'var(--bg-elevated)',
                borderRadius: '6px',
              }}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

// 统计卡片骨架屏
export function SkeletonStatCard() {
  return (
    <Card
      style={{
        borderRadius: '8px',
        border: '1px solid var(--border-color)',
      }}
      styles={{ body: { padding: '20px' } }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
          <motion.div
            initial={{ opacity: 0.5 }}
            animate={{ opacity: [0.5, 0.8, 0.5] }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
            style={{
              width: 80,
              height: 12,
              background: 'var(--bg-elevated)',
              borderRadius: '4px',
            }}
          />
          <motion.div
            initial={{ opacity: 0.5 }}
            animate={{ opacity: [0.5, 0.8, 0.5] }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              delay: 0.1,
              ease: 'easeInOut',
            }}
            style={{
              width: 100,
              height: 32,
              background: 'var(--bg-elevated)',
              borderRadius: '4px',
            }}
          />
        </div>
        <motion.div
          initial={{ opacity: 0.5 }}
          animate={{ opacity: [0.5, 0.8, 0.5] }}
          transition={{
            duration: 1.5,
            repeat: Infinity,
            delay: 0.2,
            ease: 'easeInOut',
          }}
          style={{
            width: 44,
            height: 44,
            borderRadius: '8px',
            background: 'var(--bg-elevated)',
          }}
        />
      </div>
      <motion.div
        initial={{ opacity: 0.5 }}
        animate={{ opacity: [0.5, 0.8, 0.5] }}
        transition={{
          duration: 1.5,
          repeat: Infinity,
          delay: 0.3,
          ease: 'easeInOut',
        }}
        style={{
          marginTop: 16,
          height: 4,
          background: 'var(--bg-elevated)',
          borderRadius: '2px',
        }}
      />
    </Card>
  );
}

// 列表骨架屏
export function SkeletonList({ count = 5 }: { count?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      {Array.from({ length: count }).map((_, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.5 }}
          animate={{ opacity: [0.5, 0.8, 0.5] }}
          transition={{
            duration: 1.5,
            repeat: Infinity,
            delay: i * 0.05,
            ease: 'easeInOut',
          }}
          style={{
            padding: '16px 20px',
            background: 'var(--bg-secondary)',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '6px',
              background: 'var(--bg-elevated)',
            }}
          />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div
              style={{
                width: '30%',
                height: 14,
                background: 'var(--bg-elevated)',
                borderRadius: '4px',
              }}
            />
            <div
              style={{
                width: '50%',
                height: 12,
                background: 'var(--bg-elevated)',
                borderRadius: '4px',
              }}
            />
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// 表格骨架屏
export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div
      style={{ border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}
    >
      {/* 表头 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: 16,
          padding: '16px 20px',
          background: 'var(--bg-elevated)',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        {Array.from({ length: cols }).map((_, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0.5 }}
            animate={{ opacity: [0.5, 0.8, 0.5] }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              delay: i * 0.05,
              ease: 'easeInOut',
            }}
            style={{
              height: 14,
              background: 'var(--bg-hover)',
              borderRadius: '4px',
            }}
          />
        ))}
      </div>
      {/* 表体 */}
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div
          key={rowIndex}
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${cols}, 1fr)`,
            gap: 16,
            padding: '16px 20px',
            background: 'var(--bg-secondary)',
            borderBottom: rowIndex < rows - 1 ? '1px solid var(--border-color)' : undefined,
          }}
        >
          {Array.from({ length: cols }).map((_, colIndex) => (
            <motion.div
              key={colIndex}
              initial={{ opacity: 0.5 }}
              animate={{ opacity: [0.5, 0.8, 0.5] }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                delay: (rowIndex * cols + colIndex) * 0.02,
                ease: 'easeInOut',
              }}
              style={{
                height: 14,
                width: colIndex === 0 ? '80%' : '100%',
                background: 'var(--bg-elevated)',
                borderRadius: '4px',
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
