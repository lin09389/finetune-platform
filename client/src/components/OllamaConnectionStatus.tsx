import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Badge, Button, Popover, Space, Typography } from 'antd';
import React from 'react';
import { useOllamaConnection } from '../hooks/chat/useOllamaConnection';

const { Text } = Typography;

interface OllamaConnectionStatusProps {
  showDetails?: boolean;
  onStatusChange?: (status: 'connected' | 'disconnected' | 'connecting' | 'error') => void;
}

export const OllamaConnectionStatus: React.FC<OllamaConnectionStatusProps> = ({
  showDetails = true,
  onStatusChange,
}) => {
  const { status, isConnected, isCircuitOpen, failureCount, lastCheck, reconnect, checkHealth } =
    useOllamaConnection({ onStatusChange });

  const getStatusIcon = () => {
    switch (status) {
      case 'connected':
        return <CheckCircleOutlined style={{ color: 'var(--success)' }} />;
      case 'connecting':
        return <LoadingOutlined style={{ color: 'var(--accent-primary)' }} />;
      case 'error':
        return <CloseCircleOutlined style={{ color: 'var(--error)' }} />;
      case 'disconnected':
      default:
        return <WarningOutlined style={{ color: 'var(--warning)' }} />;
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'connected':
        return 'Ollama 已连接';
      case 'connecting':
        return 'Ollama 连接中...';
      case 'error':
        return 'Ollama 连接失败';
      case 'disconnected':
      default:
        return 'Ollama 未连接';
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case 'connected':
        return 'success';
      case 'connecting':
        return 'processing';
      case 'error':
        return 'error';
      case 'disconnected':
      default:
        return 'warning';
    }
  };

  const content = (
    <Space direction="vertical" size="small" style={{ minWidth: 200 }}>
      <div>
        <Text strong>状态: </Text>
        <Text>{getStatusText()}</Text>
      </div>

      {isCircuitOpen && (
        <div>
          <Text type="danger">断路器已打开</Text>
        </div>
      )}

      {failureCount > 0 && (
        <div>
          <Text type="warning">失败次数: {failureCount}</Text>
        </div>
      )}

      {lastCheck > 0 && (
        <div>
          <Text type="secondary">上次检查: {new Date(lastCheck).toLocaleTimeString()}</Text>
        </div>
      )}

      <Space>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={checkHealth}
          disabled={status === 'connecting'}
        >
          刷新
        </Button>

        {!isConnected && (
          <Button
            size="small"
            type="primary"
            onClick={reconnect}
            disabled={status === 'connecting'}
          >
            重连
          </Button>
        )}
      </Space>
    </Space>
  );

  if (!showDetails) {
    return <Badge status={getStatusColor()} text={getStatusText()} />;
  }

  return (
    <Popover content={content} title="Ollama 连接状态" trigger="hover">
      <Space style={{ cursor: 'pointer' }}>
        {getStatusIcon()}
        <Text>{getStatusText()}</Text>
      </Space>
    </Popover>
  );
};
