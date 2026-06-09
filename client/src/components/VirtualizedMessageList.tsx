/**
 * 虚拟化消息列表组件
 *
 * 功能：
 * - 虚拟滚动优化大量消息渲染
 * - 消息分页加载
 * - 平滑滚动
 */
import { LoadingOutlined } from '@ant-design/icons';
import { Empty, Spin } from 'antd';
import React, { memo, useCallback, useEffect, useRef, useState } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

interface VirtualizedMessageListProps {
  messages: Message[];
  renderItem: (message: Message, index: number) => React.ReactNode;
  loading?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  estimatedItemHeight?: number;
  overscan?: number;
  style?: React.CSSProperties;
}

const VirtualizedMessageList: React.FC<VirtualizedMessageListProps> = ({
  messages,
  renderItem,
  loading = false,
  hasMore = false,
  onLoadMore,
  estimatedItemHeight = 100,
  overscan = 5,
  style,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(0);
  const [isScrolling, setIsScrolling] = useState(false);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const lastMessageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      if (entries[0]) {
        setContainerHeight(entries[0].contentRect.height);
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (lastMessageRef.current && messages.length > 0) {
      lastMessageRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length]);

  const handleScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      const target = e.currentTarget;
      setScrollTop(target.scrollTop);
      setIsScrolling(true);

      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }

      scrollTimeoutRef.current = setTimeout(() => {
        setIsScrolling(false);
      }, 150);

      if (hasMore && onLoadMore && target.scrollTop < 100) {
        onLoadMore();
      }
    },
    [hasMore, onLoadMore],
  );

  const totalHeight = messages.length * estimatedItemHeight;
  const startIndex = Math.max(0, Math.floor(scrollTop / estimatedItemHeight) - overscan);
  const endIndex = Math.min(
    messages.length - 1,
    Math.floor((scrollTop + containerHeight) / estimatedItemHeight) + overscan,
  );

  const visibleMessages = messages.slice(startIndex, endIndex + 1);
  const offsetY = startIndex * estimatedItemHeight;

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{
        height: '100%',
        overflow: 'auto',
        position: 'relative',
        ...style,
      }}
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: 20 }}>
          <Spin indicator={<LoadingOutlined spin />} />
        </div>
      )}

      {messages.length === 0 && !loading && (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无消息"
          style={{ marginTop: 100 }}
        />
      )}

      {messages.length > 0 && (
        <div
          style={{
            height: totalHeight,
            position: 'relative',
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: offsetY,
              left: 0,
              right: 0,
            }}
          >
            {visibleMessages.map((message, index) => {
              const actualIndex = startIndex + index;
              const isLast = actualIndex === messages.length - 1;

              return (
                <div
                  key={message.id}
                  ref={isLast ? lastMessageRef : undefined}
                  style={{
                    minHeight: estimatedItemHeight,
                    marginBottom: 8,
                  }}
                >
                  {renderItem(message, actualIndex)}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {isScrolling && (
        <div
          style={{
            position: 'sticky',
            bottom: 10,
            right: 10,
            float: 'right',
            background: 'rgba(0,0,0,0.6)',
            color: 'var(--text-inverse)',
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 12,
          }}
        >
          {startIndex + 1} - {Math.min(endIndex + 1, messages.length)} / {messages.length}
        </div>
      )}
    </div>
  );
};

export default memo(VirtualizedMessageList);
