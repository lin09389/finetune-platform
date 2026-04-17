import {
  DashboardOutlined,
  ReloadOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Progress,
  Row,
  Select,
  Slider,
  Statistic,
  Switch,
  Tag,
  Tooltip,
} from 'antd';
import React, { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL } from '../services/api';

interface PerformanceMetrics {
  tokensPerSecond: number;
  firstTokenLatency: number;
  memoryUsage: number;
  gpuUtilization: number;
  cacheHitRate: number;
  batchSize: number;
  queueLength: number;
}

interface EngineConfig {
  engine: 'huggingface' | 'vllm' | 'ollama';
  quantization: 'none' | 'gptq' | 'awq' | 'gguf' | 'int8' | 'int4';
  batchSize: number;
  maxTokens: number;
  temperature: number;
  useCache: boolean;
  flashAttention: boolean;
}

interface OptimizationSuggestion {
  type: 'performance' | 'memory' | 'quality';
  title: string;
  description: string;
  impact: 'high' | 'medium' | 'low';
  suggestedValue?: unknown;
}

interface PerformanceApiMetrics {
  average_latency_ms?: number;
  tokens_per_second?: number;
  gpu_memory_used_mb?: number;
  gpu_utilization_percent?: number;
  queue_length?: number;
}

interface SuggestionApiItem {
  category?: string;
  suggestion?: string;
  impact?: string;
  priority?: string;
}

const PerformanceMonitor: React.FC = () => {
  const [engine, setEngine] = useState<string>('huggingface');
  const [metrics, setMetrics] = useState<PerformanceMetrics>({
    tokensPerSecond: 0,
    firstTokenLatency: 0,
    memoryUsage: 0,
    gpuUtilization: 0,
    cacheHitRate: 0,
    batchSize: 1,
    queueLength: 0,
  });
  const [config, setConfig] = useState<EngineConfig>({
    engine: 'huggingface',
    quantization: 'none',
    batchSize: 1,
    maxTokens: 2048,
    temperature: 0.7,
    useCache: true,
    flashAttention: false,
  });
  const [suggestions, setSuggestions] = useState<OptimizationSuggestion[]>([]);

  const mapMetrics = (data: PerformanceApiMetrics): PerformanceMetrics => ({
    tokensPerSecond: Number(data.tokens_per_second || 0),
    firstTokenLatency: Number(data.average_latency_ms || 0),
    memoryUsage: Number(data.gpu_memory_used_mb || 0),
    gpuUtilization: Number(data.gpu_utilization_percent || 0),
    cacheHitRate: 0,
    batchSize: config.batchSize,
    queueLength: Number(data.queue_length || 0),
  });

  const mapSuggestion = (item: SuggestionApiItem): OptimizationSuggestion => ({
    type: item.category === 'memory' ? 'memory' : 'performance',
    title: item.category ? `${item.category.toUpperCase()} 优化建议` : '优化建议',
    description: item.suggestion || '暂无说明',
    impact: item.priority === 'high' ? 'high' : item.priority === 'medium' ? 'medium' : 'low',
  });

  const fetchMetrics = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/inference/performance/metrics`);
      if (!response.ok) return;

      const data = await response.json();
      setMetrics((prev) => ({
        ...prev,
        ...mapMetrics(data),
      }));
    } catch (error) {
      console.error('Failed to fetch metrics:', error);
    }
  }, [config.batchSize]);

  const fetchSuggestions = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/inference/performance/suggestions`);
      if (!response.ok) return;

      const data: SuggestionApiItem[] = await response.json();
      setSuggestions((data || []).map(mapSuggestion));
    } catch (error) {
      console.error('Failed to fetch suggestions:', error);
    }
  }, []);

  useEffect(() => {
    void fetchMetrics();
    const interval = setInterval(() => {
      void fetchMetrics();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchMetrics]);

  useEffect(() => {
    void fetchSuggestions();
  }, [fetchSuggestions]);

  const handleEngineChange = (value: string) => {
    setEngine(value);
    setConfig((prev) => ({ ...prev, engine: value as EngineConfig['engine'] }));
  };

  const handleConfigChange = (key: keyof EngineConfig, value: unknown) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const getPerformanceColor = (value: number, thresholds: [number, number]) => {
    if (value >= thresholds[1]) return '#52c41a';
    if (value >= thresholds[0]) return '#faad14';
    return '#ff4d4f';
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

  return (
    <div className="performance-monitor">
      <Card
        title={
          <span>
            <DashboardOutlined /> 性能监控面板
          </span>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void fetchMetrics()}>
            刷新
          </Button>
        }
      >
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Alert
              message="推理引擎选择"
              description={
                <div>
                  <Select
                    value={engine}
                    onChange={handleEngineChange}
                    style={{ width: 220, marginRight: 16 }}
                    options={[
                      { value: 'huggingface', label: 'HuggingFace（默认）' },
                      { value: 'vllm', label: 'vLLM（高性能）' },
                      { value: 'ollama', label: 'Ollama（本地）' },
                    ]}
                  />
                  <Tooltip title="vLLM 通常有更高吞吐，但需要额外安装与兼容性验证。">
                    <Tag color="blue">推荐：vLLM</Tag>
                  </Tooltip>
                </div>
              }
              type="info"
              showIcon
            />
          </Col>
        </Row>

        <Divider />

        <Row gutter={[16, 16]}>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="推理速度"
                value={metrics.tokensPerSecond}
                suffix="tokens/s"
                valueStyle={{ color: getPerformanceColor(metrics.tokensPerSecond, [30, 50]) }}
                prefix={<ThunderboltOutlined />}
              />
              <Progress
                percent={Math.min(100, (metrics.tokensPerSecond / 60) * 100)}
                showInfo={false}
                strokeColor={getPerformanceColor(metrics.tokensPerSecond, [30, 50])}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="平均延迟"
                value={metrics.firstTokenLatency}
                suffix="ms"
                valueStyle={{
                  color: getPerformanceColor(500 - metrics.firstTokenLatency, [200, 300]),
                }}
              />
              <Progress
                percent={Math.min(100, ((500 - metrics.firstTokenLatency) / 400) * 100)}
                showInfo={false}
                strokeColor={getPerformanceColor(500 - metrics.firstTokenLatency, [200, 300])}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="显存占用"
                value={metrics.memoryUsage}
                suffix="MB"
                valueStyle={{
                  color: getPerformanceColor(12000 - metrics.memoryUsage, [2000, 6000]),
                }}
              />
              <Progress
                percent={Math.min(100, metrics.memoryUsage / 120)}
                showInfo={false}
                strokeColor={getPerformanceColor(12000 - metrics.memoryUsage, [2000, 6000])}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="GPU 利用率"
                value={metrics.gpuUtilization}
                suffix="%"
                valueStyle={{ color: getPerformanceColor(metrics.gpuUtilization, [50, 80]) }}
              />
              <Progress
                percent={metrics.gpuUtilization}
                showInfo={false}
                strokeColor={getPerformanceColor(metrics.gpuUtilization, [50, 80])}
              />
            </Card>
          </Col>
        </Row>

        <Divider />

        <Card
          title={
            <span>
              <SettingOutlined /> 配置优化
            </span>
          }
          size="small"
        >
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <div style={{ marginBottom: 16 }}>
                <span>量化方式：</span>
                <Select
                  value={config.quantization}
                  onChange={(value) => handleConfigChange('quantization', value)}
                  style={{ width: 180, marginLeft: 8 }}
                  options={[
                    { value: 'none', label: '无量化（FP16）' },
                    { value: 'int8', label: 'INT8 量化' },
                    { value: 'int4', label: 'INT4 量化' },
                    { value: 'gptq', label: 'GPTQ' },
                    { value: 'awq', label: 'AWQ' },
                    { value: 'gguf', label: 'GGUF' },
                  ]}
                />
              </div>
              <div style={{ marginBottom: 16 }}>
                <span>批处理大小：</span>
                <Slider
                  value={config.batchSize}
                  onChange={(value) => handleConfigChange('batchSize', value)}
                  min={1}
                  max={32}
                  marks={{ 1: '1', 8: '8', 16: '16', 32: '32' }}
                  style={{ width: 220, display: 'inline-block', marginLeft: 8 }}
                />
              </div>
            </Col>
            <Col span={12}>
              <div style={{ marginBottom: 16 }}>
                <span>Flash Attention：</span>
                <Switch
                  checked={config.flashAttention}
                  onChange={(value) => handleConfigChange('flashAttention', value)}
                  style={{ marginLeft: 8 }}
                />
                <Tooltip title="启用 Flash Attention 2 通常可以改善推理吞吐。">
                  <Tag color="blue" style={{ marginLeft: 8 }}>
                    推荐开启
                  </Tag>
                </Tooltip>
              </div>
              <div style={{ marginBottom: 16 }}>
                <span>KV Cache：</span>
                <Switch
                  checked={config.useCache}
                  onChange={(value) => handleConfigChange('useCache', value)}
                  style={{ marginLeft: 8 }}
                />
              </div>
            </Col>
          </Row>
        </Card>

        {suggestions.length > 0 && (
          <>
            <Divider />
            <Card title="优化建议" size="small">
              {suggestions.map((suggestion, index) => (
                <Alert
                  key={`${suggestion.title}-${index}`}
                  message={
                    <span>
                      <Tag color={getImpactColor(suggestion.impact)}>
                        {suggestion.impact.toUpperCase()}
                      </Tag>
                      {suggestion.title}
                    </span>
                  }
                  description={suggestion.description}
                  type={suggestion.type === 'performance' ? 'success' : 'info'}
                  showIcon
                  style={{ marginBottom: 8 }}
                />
              ))}
            </Card>
          </>
        )}
      </Card>
    </div>
  );
};

export default PerformanceMonitor;
