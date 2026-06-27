import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Space, Tag } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL } from '../services/api';

interface SwiftStatus {
  available: boolean;
  version: string;
  message: string;
}

interface SwiftCheckerProps {
  onStatusChange?: (status: SwiftStatus) => void;
}

/**
 * P2-2: SWIFT 框架状态检查器
 */
export const SwiftChecker: React.FC<SwiftCheckerProps> = ({ onStatusChange }) => {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<SwiftStatus | null>(null);

  const checkSwift = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/training/check-swift`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setStatus(data);
      onStatusChange?.(data);
    } catch {
      setStatus({
        available: false,
        version: '',
        message: '检查失败',
      });
    } finally {
      setLoading(false);
    }
  }, [onStatusChange]);

  useEffect(() => {
    checkSwift();
  }, [checkSwift]);

  if (loading) {
    return (
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <ThunderboltOutlined spin />
          <span>检查 SWIFT 框架...</span>
        </Space>
      </Card>
    );
  }

  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={
        <Space>
          <ThunderboltOutlined style={{ color: status?.available ? '#52c41a' : '#ff4d4f' }} />
          <span>阿里 SWIFT 框架</span>
        </Space>
      }
      extra={
        <Button type="text" icon={<ReloadOutlined />} onClick={checkSwift} disabled={loading} />
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size="small">
        <div>
          <strong>状态:</strong>{' '}
          {status?.available ? (
            <Tag icon={<CheckCircleOutlined />} color="success">
              已安装
            </Tag>
          ) : (
            <Tag icon={<CloseCircleOutlined />} color="error">
              未安装
            </Tag>
          )}
        </div>

        {status?.version && (
          <div>
            <strong>版本:</strong> <Tag>{status.version}</Tag>
          </div>
        )}

        {status?.message && <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{status.message}</div>}

        {!status?.available && (
          <Alert
            type="warning"
            message="SWIFT 未安装"
            description={
              <div>
                <p>请运行以下命令安装：</p>
                <code style={{ background: '#f5f5f5', padding: '4px 8px', borderRadius: 4 }}>
                  pip install ms-swift -U
                </code>
              </div>
            }
            showIcon
            style={{ marginTop: 8 }}
          />
        )}
      </Space>
    </Card>
  );
};

export default SwiftChecker;
