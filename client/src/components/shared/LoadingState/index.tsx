import { Card, Skeleton, Spin } from 'antd';
import React, { memo } from 'react';

export type LoadingType = 'spinner' | 'skeleton' | 'dots' | 'card' | 'page';

export interface LoadingStateProps {
  type?: LoadingType;
  loading?: boolean;
  children?: React.ReactNode;
  tip?: string;
  size?: 'small' | 'default' | 'large';
  delay?: number;
  className?: string;
  style?: React.CSSProperties;
}

const LoadingState: React.FC<LoadingStateProps> = memo(
  ({
    type = 'spinner',
    loading = true,
    children,
    tip,
    size = 'default',
    delay,
    className,
    style,
  }) => {
    if (!loading && children) {
      return <>{children}</>;
    }

    const sizeMap = {
      small: 16,
      default: 24,
      large: 32,
    };

    const spinnerSize = sizeMap[size];

    if (type === 'spinner') {
      return (
        <div
          role="status"
          aria-live="polite"
          aria-label={tip || '正在加载'}
          className={className}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 'var(--space-8)',
            ...style,
          }}
        >
          <Spin size={size} delay={delay} aria-hidden />
          {tip ? (
            <span style={{ marginTop: 'var(--space-3)', color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
              {tip}
            </span>
          ) : null}
        </div>
      );
    }

    if (type === 'dots') {
      return (
        <div
          role="status"
          aria-live="polite"
          aria-label={tip || '正在加载'}
          className={className}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 4,
            padding: 'var(--space-4)',
            ...style,
          }}
        >
          <div className="dots-loader">
            <span />
            <span />
            <span />
          </div>
          {tip && <span style={{ marginLeft: 8, color: 'var(--text-secondary)' }}>{tip}</span>}
        </div>
      );
    }

    if (type === 'skeleton') {
      return (
        <div role="status" aria-live="polite" aria-label={tip || '正在加载'} className={className} style={style}>
          <Skeleton active paragraph={{ rows: 4 }} />
        </div>
      );
    }

    if (type === 'card') {
      return (
        <Card role="status" aria-live="polite" aria-label={tip || '正在加载'} className={className} style={style}>
          <Skeleton active avatar paragraph={{ rows: 3 }} />
        </Card>
      );
    }

    if (type === 'page') {
      return (
        <div
          role="status"
          aria-live="polite"
          aria-label={tip || '正在加载'}
          className={className}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100%',
            height: '100%',
            gap: 24,
            background: 'var(--bg-primary)',
            ...style,
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 'var(--radius-xl)',
              background: 'var(--text-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 28,
              color: 'var(--text-inverse)',
            }}
          >
            <Spin
              indicator={
                <div
                  style={{
                    width: spinnerSize,
                    height: spinnerSize,
                    border: '2px solid var(--text-inverse)',
                    borderTopColor: 'transparent',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                  }}
                />
              }
            />
          </div>
          <div style={{ textAlign: 'center' }}>
            <div
              style={{
                fontSize: 'var(--text-lg)',
                fontWeight: 600,
                color: 'var(--text-primary)',
                marginBottom: 8,
              }}
            >
              {tip || '正在加载...'}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>请稍候</div>
          </div>
        </div>
      );
    }

    return null;
  },
);

LoadingState.displayName = 'LoadingState';

export default LoadingState;

export const Spinner: React.FC<{
  size?: 'small' | 'default' | 'large';
  tip?: string;
}> = memo(({ size = 'default', tip }) => <LoadingState type="spinner" size={size} tip={tip} />);

Spinner.displayName = 'Spinner';

export const SkeletonCard: React.FC<{
  count?: number;
}> = memo(({ count = 1 }) => (
  <>
    {Array.from({ length: count }).map((_, i) => (
      <Card key={i} style={{ marginBottom: 'var(--space-4)' }}>
        <Skeleton active avatar paragraph={{ rows: 3 }} />
      </Card>
    ))}
  </>
));

SkeletonCard.displayName = 'SkeletonCard';

export const SkeletonTable: React.FC<{
  rows?: number;
  columns?: number;
}> = memo(({ rows = 5, columns = 4 }) => (
  <div>
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: 'var(--space-4)',
        padding: 'var(--space-4)',
        background: 'var(--bg-elevated)',
        borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0',
        borderBottom: '1px solid var(--border-color)',
      }}
    >
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton.Input key={i} active size="small" style={{ width: '100%' }} />
      ))}
    </div>
    {Array.from({ length: rows }).map((_, rowIndex) => (
      <div
        key={rowIndex}
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${columns}, 1fr)`,
          gap: 'var(--space-4)',
          padding: 'var(--space-4)',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        {Array.from({ length: columns }).map((_, colIndex) => (
          <Skeleton.Input key={colIndex} active size="small" style={{ width: '100%' }} />
        ))}
      </div>
    ))}
  </div>
));

SkeletonTable.displayName = 'SkeletonTable';

export const SkeletonList: React.FC<{
  count?: number;
}> = memo(({ count = 3 }) => (
  <div>
    {Array.from({ length: count }).map((_, i) => (
      <div
        key={i}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-3)',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        <Skeleton.Avatar active />
        <div style={{ flex: 1 }}>
          <Skeleton active paragraph={{ rows: 1 }} />
        </div>
      </div>
    ))}
  </div>
));

SkeletonList.displayName = 'SkeletonList';

export const InlineLoading: React.FC<{
  loading?: boolean;
  children: React.ReactNode;
}> = memo(({ loading, children }) => (
  <Spin spinning={loading} size="small">
    {children}
  </Spin>
));

InlineLoading.displayName = 'InlineLoading';
