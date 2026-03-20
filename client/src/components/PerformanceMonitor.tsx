/**
 * 性能监控面板组件
 * 
 * 功能：
 * - 推理引擎选择
 * - 性能指标显示
 * - 配置优化建议
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Select,
  Statistic,
  Row,
  Col,
  Progress,
  Tag,
  Button,
  Tooltip,
  Alert,
  Switch,
  Slider,
  Divider,
} from 'antd';
import {
  ThunderboltOutlined,
  DashboardOutlined,
  SettingOutlined,
  ReloadOutlined,
} from '@ant-design/icons';

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
  suggestedValue?: any;
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

  const fetchMetrics = useCallback(async () => {
    try {
      const response = await fetch('/api/inference/metrics');
      if (response.ok) {
        const data = await response.json();
        setMetrics(data);
      }
    } catch (error) {
      console.error('Failed to fetch metrics:', error);
    }
  }, []);

  const fetchSuggestions = useCallback(async () => {
    try {
      const response = await fetch('/api/inference/suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (response.ok) {
        const data = await response.json();
        setSuggestions(data.suggestions || []);
      }
    } catch (error) {
      console.error('Failed to fetch suggestions:', error);
    }
  }, [config]);

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000);
    return () => clearInterval(interval);
  }, [fetchMetrics]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  const handleEngineChange = (value: string) => {
    setEngine(value);
    setConfig(prev => ({ ...prev, engine: value as any }));
  };

  const handleConfigChange = (key: keyof EngineConfig, value: any) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  };

  const applySuggestion = (suggestion: OptimizationSuggestion) => {
    if (suggestion.suggestedValue !== undefined) {
      const keyMap: Record<string, keyof EngineConfig> = {
        'quantization': 'quantization',
        'batch_size': 'batchSize',
        'max_tokens': 'maxTokens',
        'flash_attention': 'flashAttention',
        'use_cache': 'useCache',
      };
      
      const key = Object.keys(keyMap).find(k => 
        suggestion.title.toLowerCase().includes(k.replace('_', ' '))
      );
      
      if (key && keyMap[key]) {
        handleConfigChange(keyMap[key], suggestion.suggestedValue);
      }
    }
  };

  const getPerformanceColor = (value: number, thresholds: [number, number]) => {
    if (value >= thresholds[1]) return '#52c41a';
    if (value >= thresholds[0]) return '#faad14';
    return '#ff4d4f';
  };

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case 'high': return 'red';
      case 'medium': return 'orange';
      case 'low': return 'green';
      default: return 'default';
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
          <Button icon={<ReloadOutlined />} onClick={fetchMetrics}>
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
                    style={{ width: 200, marginRight: 16 }}
                    options={[
                      { value: 'huggingface', label: 'HuggingFace (默认)' },
                      { value: 'vllm', label: 'vLLM (高性能)' },
                      { value: 'ollama', label: 'Ollama (本地)' },
                    ]}
                  />
                  <Tooltip title="vLLM 提供最高性能，但需要额外安装">
                    <Tag color="blue">推荐: vLLM</Tag>
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
                valueStyle={{
                  color: getPerformanceColor(metrics.tokensPerSecond, [30, 50]),
                }}
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
                title="首字延迟"
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
                suffix="%"
                valueStyle={{
                  color: getPerformanceColor(100 - metrics.memoryUsage, [30, 50]),
                }}
              />
              <Progress
                percent={metrics.memoryUsage}
                showInfo={false}
                strokeColor={getPerformanceColor(100 - metrics.memoryUsage, [30, 50])}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="缓存命中率"
                value={metrics.cacheHitRate * 100}
                suffix="%"
                valueStyle={{
                  color: getPerformanceColor(metrics.cacheHitRate * 100, [50, 80]),
                }}
              />
              <Progress
                percent={metrics.cacheHitRate * 100}
                showInfo={false}
                strokeColor={getPerformanceColor(metrics.cacheHitRate * 100, [50, 80])}
              />
            </Card>
          </Col>
        </Row>

        <Divider />

        <Card title={<span><SettingOutlined /> 配置优化</span>} size="small">
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <div style={{ marginBottom: 16 }}>
                <span>量化方式：</span>
                <Select
                  value={config.quantization}
                  onChange={(v) => handleConfigChange('quantization', v)}
                  style={{ width: 150, marginLeft: 8 }}
                  options={[
                    { value: 'none', label: '无量化 (FP16)' },
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
                  onChange={(v) => handleConfigChange('batchSize', v)}
                  min={1}
                  max={32}
                  marks={{ 1: '1', 8: '8', 16: '16', 32: '32' }}
                  style={{ width: 200, display: 'inline-block', marginLeft: 8 }}
                />
              </div>
            </Col>
            <Col span={12}>
              <div style={{ marginBottom: 16 }}>
                <span>Flash Attention：</span>
                <Switch
                  checked={config.flashAttention}
                  onChange={(v) => handleConfigChange('flashAttention', v)}
                  style={{ marginLeft: 8 }}
                />
                <Tooltip title="启用 Flash Attention 2 可显著提升推理速度">
                  <Tag color="blue" style={{ marginLeft: 8 }}>推荐开启</Tag>
                </Tooltip>
              </div>
              <div style={{ marginBottom: 16 }}>
                <span>KV Cache：</span>
                <Switch
                  checked={config.useCache}
                  onChange={(v) => handleConfigChange('useCache', v)}
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
                  key={index}
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
                  action={
                    suggestion.suggestedValue !== undefined && (
                      <Button size="small" onClick={() => applySuggestion(suggestion)}>
                        应用
                      </Button>
                    )
                  }
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
