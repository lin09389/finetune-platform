/**
 * 配置优化建议组件
 *
 * 功能：
 * - 显示优化建议列表
 * - 一键应用建议
 * - 建议影响评估
 */
import {
  BulbOutlined,
  CheckOutlined,
  DashboardOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Button, Card, Collapse, Descriptions, Empty, Progress, Space, Tag } from 'antd';
import React from 'react';

interface OptimizationSuggestion {
  id: string;
  type: 'performance' | 'memory' | 'quality' | 'security';
  title: string;
  description: string;
  impact: 'high' | 'medium' | 'low';
  currentValue?: any;
  suggestedValue?: any;
  estimatedImprovement?: string;
  applied?: boolean;
}

interface OptimizationSuggestionsProps {
  suggestions: OptimizationSuggestion[];
  onApply: (suggestion: OptimizationSuggestion) => void;
  onApplyAll?: () => void;
  loading?: boolean;
}

const getTypeIcon = (type: string) => {
  switch (type) {
    case 'performance':
      return <ThunderboltOutlined style={{ color: '#faad14' }} />;
    case 'memory':
      return <DashboardOutlined style={{ color: '#1890ff' }} />;
    case 'quality':
      return <SafetyOutlined style={{ color: '#52c41a' }} />;
    default:
      return <BulbOutlined style={{ color: '#722ed1' }} />;
  }
};

const getImpactColor = (impact: string) => {
  switch (impact) {
    case 'high':
      return 'red';
    case 'medium':
      return 'orange';
    case 'low':
      return 'green';
    default:
      return 'default';
  }
};

const getImpactLabel = (impact: string) => {
  switch (impact) {
    case 'high':
      return '高影响';
    case 'medium':
      return '中影响';
    case 'low':
      return '低影响';
    default:
      return '未知';
  }
};

const OptimizationSuggestions: React.FC<OptimizationSuggestionsProps> = ({
  suggestions,
  onApply,
  onApplyAll,
  loading = false,
}) => {
  const highImpactSuggestions = suggestions.filter((s) => s.impact === 'high' && !s.applied);
  const appliedCount = suggestions.filter((s) => s.applied).length;

  if (suggestions.length === 0) {
    return (
      <Card
        title={
          <Space>
            <BulbOutlined />
            <span>优化建议</span>
          </Space>
        }
        size="small"
      >
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无优化建议" />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          <BulbOutlined />
          <span>优化建议</span>
          <Tag color="blue">{suggestions.length} 条</Tag>
        </Space>
      }
      size="small"
      extra={
        highImpactSuggestions.length > 0 &&
        onApplyAll && (
          <Button type="primary" size="small" onClick={onApplyAll} loading={loading}>
            应用全部高影响建议
          </Button>
        )
      }
    >
      {appliedCount > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
            <span>已应用建议</span>
            <span>
              {appliedCount}/{suggestions.length}
            </span>
          </div>
          <Progress
            percent={Math.round((appliedCount / suggestions.length) * 100)}
            size="small"
            status={appliedCount === suggestions.length ? 'success' : 'active'}
          />
        </div>
      )}

      <Collapse
        accordion
        items={suggestions.map((suggestion) => ({
          key: suggestion.id,
          label: (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Space>
                {getTypeIcon(suggestion.type)}
                <span>{suggestion.title}</span>
              </Space>
              <Space>
                <Tag color={getImpactColor(suggestion.impact)}>
                  {getImpactLabel(suggestion.impact)}
                </Tag>
                {suggestion.applied && (
                  <Tag icon={<CheckOutlined />} color="success">
                    已应用
                  </Tag>
                )}
              </Space>
            </div>
          ),
          children: (
            <div>
              <p style={{ marginBottom: 16 }}>{suggestion.description}</p>

              <Descriptions column={1} size="small">
                {suggestion.currentValue !== undefined && (
                  <Descriptions.Item label="当前值">
                    <Tag>{String(suggestion.currentValue)}</Tag>
                  </Descriptions.Item>
                )}
                {suggestion.suggestedValue !== undefined && (
                  <Descriptions.Item label="建议值">
                    <Tag color="green">{String(suggestion.suggestedValue)}</Tag>
                  </Descriptions.Item>
                )}
                {suggestion.estimatedImprovement && (
                  <Descriptions.Item label="预期提升">
                    <Tag color="blue">{suggestion.estimatedImprovement}</Tag>
                  </Descriptions.Item>
                )}
              </Descriptions>

              {!suggestion.applied && (
                <Button
                  type="primary"
                  size="small"
                  onClick={() => onApply(suggestion)}
                  loading={loading}
                  style={{ marginTop: 12 }}
                >
                  应用此建议
                </Button>
              )}
            </div>
          ),
        }))}
      />
    </Card>
  );
};

export default OptimizationSuggestions;
