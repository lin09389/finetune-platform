import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  PauseCircleOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import { Badge, Progress, Space, Tooltip, Typography } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import React from 'react';
import { ConnectionState, StreamState } from '../services/StreamManager';

const { Text } = Typography;

interface ConnectionStatusProps {
  state: StreamState;
  showStats?: boolean;
  compact?: boolean;
}

const stateConfig: Record<
  ConnectionState,
  {
    color: string;
    status: 'success' | 'processing' | 'error' | 'warning' | 'default';
    icon: React.ReactNode;
    text: string;
  }
> = {
  [ConnectionState.IDLE]: {
    color: '#8c8c8c',
    status: 'default',
    icon: <PauseCircleOutlined />,
    text: '空闲',
  },
  [ConnectionState.CONNECTING]: {
    color: '#1890ff',
    status: 'processing',
    icon: <LoadingOutlined spin />,
    text: '连接中...',
  },
  [ConnectionState.CONNECTED]: {
    color: '#52c41a',
    status: 'success',
    icon: <CheckCircleOutlined />,
    text: '已连接',
  },
  [ConnectionState.STREAMING]: {
    color: '#1890ff',
    status: 'processing',
    icon: <ThunderboltOutlined />,
    text: '接收中',
  },
  [ConnectionState.RECONNECTING]: {
    color: '#faad14',
    status: 'warning',
    icon: <SyncOutlined spin />,
    text: '重连中',
  },
  [ConnectionState.DISCONNECTED]: {
    color: '#8c8c8c',
    status: 'default',
    icon: <CloseCircleOutlined />,
    text: '已断开',
  },
  [ConnectionState.ERROR]: {
    color: '#ff4d4f',
    status: 'error',
    icon: <CloseCircleOutlined />,
    text: '错误',
  },
};

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({
  state,
  showStats = false,
  compact = false,
}) => {
  const config = stateConfig[state.connectionState];

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const formatDuration = (startTime: number | null): string => {
    if (!startTime) return '0s';
    const seconds = Math.floor((Date.now() - startTime) / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  if (compact) {
    return (
      <Tooltip
        title={
          <Space direction="vertical" size={4}>
            <Text style={{ color: '#fff' }}>{config.text}</Text>
            {showStats && state.startTime && (
              <>
                <Text style={{ color: '#fff', fontSize: 12 }}>
                  已接收: {formatBytes(state.receivedBytes)}
                </Text>
                <Text style={{ color: '#fff', fontSize: 12 }}>分块数: {state.chunksReceived}</Text>
                <Text style={{ color: '#fff', fontSize: 12 }}>
                  时长: {formatDuration(state.startTime)}
                </Text>
              </>
            )}
            {state.error && (
              <Text style={{ color: '#ff7875', fontSize: 12 }}>错误: {state.error}</Text>
            )}
          </Space>
        }
      >
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          <Badge status={config.status} />
          <span style={{ color: config.color, fontSize: 12 }}>{config.icon}</span>
        </motion.div>
      </Tooltip>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 16px',
        background: 'var(--bg-secondary)',
        borderRadius: 8,
        border: '1px solid var(--border-color)',
      }}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={state.connectionState}
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.5, opacity: 0 }}
          transition={{ duration: 0.2 }}
          style={{ display: 'flex', alignItems: 'center', gap: 8 }}
        >
          <span style={{ color: config.color, fontSize: 16 }}>{config.icon}</span>
          <Text style={{ color: config.color, fontWeight: 500 }}>{config.text}</Text>
        </motion.div>
      </AnimatePresence>

      {showStats && state.connectionState === ConnectionState.STREAMING && (
        <motion.div
          initial={{ opacity: 0, width: 0 }}
          animate={{ opacity: 1, width: 'auto' }}
          exit={{ opacity: 0, width: 0 }}
          style={{ display: 'flex', alignItems: 'center', gap: 16 }}
        >
          <Space size={16}>
            <Tooltip title="已接收数据量">
              <Text type="secondary" style={{ fontSize: 12 }}>
                <WifiOutlined style={{ marginRight: 4 }} />
                {formatBytes(state.receivedBytes)}
              </Text>
            </Tooltip>

            <Tooltip title="已接收分块数">
              <Text type="secondary" style={{ fontSize: 12 }}>
                分块: {state.chunksReceived}
              </Text>
            </Tooltip>

            {state.startTime && (
              <Tooltip title="连接时长">
                <Text type="secondary" style={{ fontSize: 12 }}>
                  时长: {formatDuration(state.startTime)}
                </Text>
              </Tooltip>
            )}
          </Space>
        </motion.div>
      )}

      {state.connectionState === ConnectionState.RECONNECTING && (
        <Text type="warning" style={{ fontSize: 12 }}>
          第 {state.retryCount} 次重试
        </Text>
      )}

      {state.error && (
        <Text type="danger" style={{ fontSize: 12 }}>
          {state.error}
        </Text>
      )}
    </motion.div>
  );
};

interface StreamingProgressProps {
  state: StreamState;
  estimatedTotal?: number;
}

export const StreamingProgress: React.FC<StreamingProgressProps> = ({ state, estimatedTotal }) => {
  if (state.connectionState !== ConnectionState.STREAMING) {
    return null;
  }

  const progress = estimatedTotal
    ? Math.min((state.receivedBytes / estimatedTotal) * 100, 100)
    : undefined;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      style={{ marginTop: 8 }}
    >
      {progress !== undefined ? (
        <Progress
          percent={Math.round(progress)}
          size="small"
          status="active"
          format={() => `${Math.round(progress)}%`}
        />
      ) : (
        <Progress
          percent={100}
          size="small"
          status="active"
          showInfo={false}
          strokeColor={{
            '0%': '#108ee9',
            '100%': '#87d068',
          }}
        />
      )}
    </motion.div>
  );
};

interface PartialSaveIndicatorProps {
  saved: boolean;
  content: string;
  timestamp: number;
}

export const PartialSaveIndicator: React.FC<PartialSaveIndicatorProps> = ({
  saved,
  content,
  timestamp,
}) => {
  if (!saved || !content) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.8 }}
        style={{
          position: 'fixed',
          bottom: 100,
          right: 24,
          padding: '8px 16px',
          background: 'rgba(82, 196, 26, 0.9)',
          borderRadius: 8,
          color: '#fff',
          fontSize: 12,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          zIndex: 1000,
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
        }}
      >
        <CheckCircleOutlined />
        <span>已保存 {content.length} 字符</span>
        <Text style={{ color: 'rgba(255, 255, 255, 0.8)', fontSize: 11 }}>
          {new Date(timestamp).toLocaleTimeString()}
        </Text>
      </motion.div>
    </AnimatePresence>
  );
};

export default ConnectionStatus;
