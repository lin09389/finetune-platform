/**
 * 推理引擎选择组件
 *
 * 功能：
 * - 引擎选择（HuggingFace/vLLM/Ollama）
 * - 引擎状态显示
 * - 引擎切换
 */
import {
  CheckCircleOutlined,
  CloudOutlined,
  DesktopOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Badge, Card, Descriptions, Select, Space, Tag } from 'antd';
import React from 'react';

interface EngineInfo {
  id: string;
  name: string;
  description: string;
  available: boolean;
  type: 'local' | 'remote';
  features: string[];
  performance?: {
    tokensPerSecond?: number;
    latency?: number;
  };
}

interface EngineSelectorProps {
  engines: EngineInfo[];
  currentEngine: string;
  onEngineChange: (engineId: string) => void;
  loading?: boolean;
}

const getEngineIcon = (engineId: string) => {
  switch (engineId) {
    case 'vllm':
      return <ThunderboltOutlined />;
    case 'ollama':
      return <CloudOutlined />;
    default:
      return <DesktopOutlined />;
  }
};

const EngineSelector: React.FC<EngineSelectorProps> = ({
  engines,
  currentEngine,
  onEngineChange,
  loading = false,
}) => {
  const currentEngineInfo = engines.find((e) => e.id === currentEngine);

  return (
    <Card
      title={
        <Space>
          <DesktopOutlined />
          <span>推理引擎</span>
        </Space>
      }
      size="small"
      extra={
        <Badge
          status={currentEngineInfo?.available ? 'success' : 'error'}
          text={currentEngineInfo?.available ? '可用' : '不可用'}
        />
      }
    >
      <Select
        value={currentEngine}
        onChange={onEngineChange}
        style={{ width: '100%', marginBottom: 16 }}
        loading={loading}
        optionLabelProp="label"
      >
        {engines.map((engine) => (
          <Select.Option
            key={engine.id}
            value={engine.id}
            label={
              <Space>
                {getEngineIcon(engine.id)}
                <span>{engine.name}</span>
                {!engine.available && <Tag color="red">不可用</Tag>}
              </Space>
            }
            disabled={!engine.available}
          >
            <div style={{ padding: '8px 0' }}>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>
                <Space>
                  {getEngineIcon(engine.id)}
                  {engine.name}
                </Space>
              </div>
              <div style={{ fontSize: 12, color: '#999' }}>{engine.description}</div>
              <div style={{ marginTop: 8 }}>
                {engine.features.map((feature) => (
                  <Tag key={feature} style={{ marginBottom: 4 }}>
                    {feature}
                  </Tag>
                ))}
              </div>
            </div>
          </Select.Option>
        ))}
      </Select>

      {currentEngineInfo && (
        <Descriptions column={2} size="small">
          <Descriptions.Item label="类型">
            <Tag color={currentEngineInfo.type === 'local' ? 'green' : 'blue'}>
              {currentEngineInfo.type === 'local' ? '本地' : '远程'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            {currentEngineInfo.available ? (
              <Tag icon={<CheckCircleOutlined />} color="success">
                在线
              </Tag>
            ) : (
              <Tag icon={<WarningOutlined />} color="error">
                离线
              </Tag>
            )}
          </Descriptions.Item>
          {currentEngineInfo.performance?.tokensPerSecond && (
            <Descriptions.Item label="速度">
              {currentEngineInfo.performance.tokensPerSecond} t/s
            </Descriptions.Item>
          )}
          {currentEngineInfo.performance?.latency && (
            <Descriptions.Item label="延迟">
              {currentEngineInfo.performance.latency}ms
            </Descriptions.Item>
          )}
        </Descriptions>
      )}

      <div style={{ marginTop: 16, fontSize: 12, color: '#666' }}>
        <div style={{ marginBottom: 8 }}>
          <strong>引擎说明：</strong>
        </div>
        <ul style={{ paddingLeft: 16, margin: 0 }}>
          <li>
            <Tag color="#1890ff" style={{ marginRight: 4 }}>
              HuggingFace
            </Tag>
            默认引擎，兼容性好，支持所有模型
          </li>
          <li>
            <Tag color="#722ed1" style={{ marginRight: 4 }}>
              vLLM
            </Tag>
            高性能引擎，推荐用于生产环境
          </li>
          <li>
            <Tag color="#13c2c2" style={{ marginRight: 4 }}>
              Ollama
            </Tag>
            本地部署，支持多种开源模型
          </li>
        </ul>
      </div>
    </Card>
  );
};

export default EngineSelector;
