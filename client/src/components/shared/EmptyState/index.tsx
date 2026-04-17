import { FileSearchOutlined, InboxOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Empty } from 'antd';
import React, { memo } from 'react';

export type EmptyType = 'default' | 'data' | 'search' | 'error' | 'network';

export interface EmptyStateProps {
  type?: EmptyType;
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  image?: React.ReactNode;
  action?: {
    text: string;
    onClick: () => void;
    icon?: React.ReactNode;
  };
  className?: string;
  style?: React.CSSProperties;
}

const emptyConfigs: Record<
  EmptyType,
  { icon: React.ReactNode; title: string; description: string }
> = {
  default: {
    icon: <InboxOutlined style={{ fontSize: 48, color: 'var(--text-tertiary)' }} />,
    title: '暂无数据',
    description: '这里还没有任何内容',
  },
  data: {
    icon: <InboxOutlined style={{ fontSize: 48, color: 'var(--text-tertiary)' }} />,
    title: '暂无数据',
    description: '当前列表为空',
  },
  search: {
    icon: <FileSearchOutlined style={{ fontSize: 48, color: 'var(--text-tertiary)' }} />,
    title: '未找到结果',
    description: '尝试使用不同的关键词搜索',
  },
  error: {
    icon: <InboxOutlined style={{ fontSize: 48, color: 'var(--error)' }} />,
    title: '加载失败',
    description: '数据加载出错，请稍后重试',
  },
  network: {
    icon: <InboxOutlined style={{ fontSize: 48, color: 'var(--warning)' }} />,
    title: '网络错误',
    description: '请检查网络连接后重试',
  },
};

const EmptyState: React.FC<EmptyStateProps> = memo(
  ({ type = 'default', title, description, icon, image, action, className, style }) => {
    const config = emptyConfigs[type];

    return (
      <div
        className={className}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 'var(--space-12) var(--space-6)',
          textAlign: 'center',
          ...style,
        }}
      >
        {image || (
          <div
            style={{
              width: 80,
              height: 80,
              borderRadius: 'var(--radius-xl)',
              background: 'var(--bg-elevated)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 'var(--space-4)',
            }}
          >
            {icon || config.icon}
          </div>
        )}

        <h3
          style={{
            fontSize: 'var(--text-base)',
            fontWeight: 600,
            color: 'var(--text-primary)',
            margin: 0,
            marginBottom: 'var(--space-2)',
          }}
        >
          {title || config.title}
        </h3>

        <p
          style={{
            fontSize: 'var(--text-sm)',
            color: 'var(--text-secondary)',
            margin: 0,
            marginBottom: action ? 'var(--space-4)' : 0,
            maxWidth: 280,
          }}
        >
          {description || config.description}
        </p>

        {action && (
          <Button
            type="primary"
            icon={action.icon || <PlusOutlined />}
            onClick={action.onClick}
            style={{
              borderRadius: 'var(--radius-md)',
            }}
          >
            {action.text}
          </Button>
        )}
      </div>
    );
  },
);

EmptyState.displayName = 'EmptyState';

export default EmptyState;

export const DataEmpty: React.FC<{
  title?: string;
  description?: string;
  actionText?: string;
  onAction?: () => void;
}> = memo(({ title, description, actionText, onAction }) => (
  <EmptyState
    type="data"
    title={title}
    description={description}
    action={actionText && onAction ? { text: actionText, onClick: onAction } : undefined}
  />
));

DataEmpty.displayName = 'DataEmpty';

export const SearchEmpty: React.FC<{
  keyword?: string;
  onClear?: () => void;
}> = memo(({ keyword, onClear }) => (
  <EmptyState
    type="search"
    description={keyword ? `未找到与"${keyword}"相关的结果` : undefined}
    action={onClear ? { text: '清除搜索', onClick: onClear } : undefined}
  />
));

SearchEmpty.displayName = 'SearchEmpty';

export const ErrorEmpty: React.FC<{
  message?: string;
  onRetry?: () => void;
}> = memo(({ message, onRetry }) => (
  <EmptyState
    type="error"
    description={message}
    action={onRetry ? { text: '重试', onClick: onRetry } : undefined}
  />
));

ErrorEmpty.displayName = 'ErrorEmpty';

export const SimpleEmpty: React.FC<{
  description?: string;
}> = memo(({ description }) => (
  <Empty
    image={Empty.PRESENTED_IMAGE_SIMPLE}
    description={
      <span style={{ color: 'var(--text-secondary)' }}>{description || '暂无数据'}</span>
    }
  />
));

SimpleEmpty.displayName = 'SimpleEmpty';
