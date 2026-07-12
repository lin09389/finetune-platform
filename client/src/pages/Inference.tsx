import {
  ClearOutlined,
  CodeOutlined,
  LoadingOutlined,
  SendOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { Alert, Badge, Button, Col, Divider, Input, Row, Select, Slider, Space, Tag, Switch } from 'antd';
import { useEffect, useRef, useState } from 'react';
import GlassCard from '../components/shared/GlassCard';
import PageHeader from '../components/shared/PageHeader';
import StatusState from '../components/shared/StatusState';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import VersionComparisonChat from '../components/shared/VersionComparisonChat';
import { useRuntimeContext } from '../runtime/RuntimeContext';
import {
  getPerformanceRecommendations,
  streamInference,
  switchBackend,
} from '../services/api';
import { notify } from '../utils/notify';
import styles from './Inference.module.css';

const { TextArea } = Input;

type PerformanceRecommendations = {
  hardware_profile?: {
    recommended_backend?: string;
    recommended_quantization?: string;
    profile?: string;
  };
};

export default function Inference() {
  const runtime = useRuntimeContext();
  const { actions, derived, observed } = runtime;
  const { refreshInference, setInferenceSelection, syncInferenceSelection } = actions;
  const backendStatus = observed.backendStatus;
  const [selectedModel, setSelectedModel] = useState<string>();
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [temperature, setTemperature] = useState(0.7);
  const [loraAdapter, setLoraAdapter] = useState('');
  const [currentBackend, setCurrentBackend] = useState<string>(
    observed.inference.currentBackend || 'huggingface',
  );
  const [performanceContext, setPerformanceContext] = useState<PerformanceRecommendations | null>(null);
  const [comparisonMode, setComparisonMode] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void refreshInference();
    loadPerformance();
  }, [backendStatus, refreshInference]);

  useEffect(() => {
    if (observed.inference.currentBackend) {
      setCurrentBackend(
        (prev) => prev || derived.activeBackend || observed.inference.currentBackend,
      );
    }
  }, [derived.activeBackend, observed.inference.currentBackend]);

  useEffect(() => {
    if (!selectedModel && derived.activeModelId) {
      setSelectedModel(derived.activeModelId);
    }
  }, [derived.activeModelId, selectedModel]);

  useEffect(() => {
    setInferenceSelection({
      backend: currentBackend,
      modelId: selectedModel,
    });
  }, [currentBackend, selectedModel, setInferenceSelection]);

  const loadPerformance = async () => {
    const recommendations = await getPerformanceRecommendations().catch(() => null);
    setPerformanceContext(recommendations as PerformanceRecommendations | null);
  };

  const handleBackendChange = async (backend: string) => {
    try {
      await switchBackend(backend);
      setCurrentBackend(backend);
      setSelectedModel(undefined);
      syncInferenceSelection({ backend, modelId: undefined });
      await refreshInference();
      const backendLabel = observed.inference.backends.find((item) => item.id === backend)?.name || backend;
      notify.success(`已切换到 ${backendLabel} 后端`);
    } catch (error) {
      notify.error('切换失败');
    }
  };

  const modelOptions =
    currentBackend === 'ollama'
      ? observed.inference.ollamaModels.map((m) => ({ value: m.id, label: m.name }))
      : currentBackend === 'llama-cpp'
        ? observed.inference.huggingfaceModels
            .filter((m) => m.name.toLowerCase().includes('.gguf') || m.name.toLowerCase().includes('.ggml'))
            .map((m) => ({ value: m.id, label: m.name }))
        : observed.inference.huggingfaceModels.map((m) => ({
            value: m.id,
            label: m.name,
          }));

  const currentBackendInfo = observed.inference.backends.find((b) => b.id === currentBackend);
  const isBackendAvailable = currentBackendInfo?.available ?? true;
  const recommendedBackend = performanceContext?.hardware_profile?.recommended_backend;
  const recommendedQuantization = performanceContext?.hardware_profile?.recommended_quantization;
  const recommendedProfile = performanceContext?.hardware_profile?.profile;

  const handleSend = async () => {
    if (!selectedModel || !prompt.trim()) return;

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setResponse('');

    try {
      await streamInference(
        {
          modelId: selectedModel,
          prompt: prompt,
          maxTokens: maxTokens,
          temperature: temperature,
          backend: currentBackend,
          loraAdapter: loraAdapter.trim() || undefined,
        },
        (text: string) => {
          setResponse((prev) => prev + text);
        },
        undefined,
        controller.signal,
      );
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }
      const errorMsg = error instanceof Error ? error.message : '推理失败';
      setResponse(`错误: ${errorMsg}`);
    } finally {
      if (abortControllerRef.current === controller) {
        setLoading(false);
        abortControllerRef.current = null;
      }
    }
  };

  const handleClear = () => {
    setPrompt('');
    setResponse('');
  };

  const getBackendBadge = () => {
    if (currentBackend === 'ollama') {
      return (
        <Badge
          status={isBackendAvailable ? 'success' : 'error'}
          text={isBackendAvailable ? 'Ollama 已连接' : 'Ollama 未运行'}
        />
      );
    }
    return <Badge status="success" text="本地模型" />;
  };

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
        <PageHeader
          title="推理测试"
          icon={<CodeOutlined />}
          helpTooltip="与本地或 Ollama 模型进行对话测试，调整推理参数以获得最佳效果。"
          style={{ marginBottom: 0 }}
        />
      </MotionItem>

      {backendStatus !== 'connected' ? (
        <MotionItem>
          <StatusState
            tone="offline"
            title="推理服务未连接"
            description="推理测试需要本地后端。启动服务后重试，模型和参数会保留。"
            action={{ text: '重新检查连接', onClick: () => void refreshInference() }}
          />
        </MotionItem>
      ) : (
        <MotionItem>
          <Row gutter={[24, 24]}>
            <Col xs={24} lg={16}>
              <GlassCard className={styles.card}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 'var(--space-6)',
                  }}
                >
                  <Space>
                    <h3 style={{ margin: 0, fontSize: 'var(--text-lg)', color: 'var(--text-primary)' }}>对话测试</h3>
                    <Select
                      value={currentBackend}
                      onChange={handleBackendChange}
                      style={{ width: 160 }}
                      suffixIcon={<SwapOutlined />}
                      options={observed.inference.backends.map((b) => ({
                        value: b.id,
                        label: b.available ? b.name : `${b.name} (不可用)`,
                        disabled: !b.available,
                      }))}
                    />
                  </Space>
                  <Space>
                    <span style={{color: 'var(--text-secondary)'}}>A/B Comparison Mode</span>
                    <Switch 
                      checked={comparisonMode} 
                      onChange={setComparisonMode} 
                      style={{ background: comparisonMode ? 'var(--accent-primary)' : undefined }}
                    />
                  </Space>
                </div>

                {!isBackendAvailable && currentBackend === 'ollama' && (
                  <Alert
                    type="warning"
                    message="Ollama 未运行"
                    description="请确保 Ollama 已启动，然后刷新页面"
                    showIcon
                    style={{ marginBottom: 'var(--space-4)', borderRadius: 'var(--radius-sm)' }}
                    action={
                      <Button size="small" onClick={() => void refreshInference()}>
                        刷新
                      </Button>
                    }
                  />
                )}

                {recommendedBackend && recommendedBackend !== currentBackend && (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 'var(--space-4)', borderRadius: 'var(--radius-sm)' }}
                    message={`当前设备推荐优先使用 ${recommendedBackend}`}
                    description={`硬件档位：${recommendedProfile || 'unknown'}，推荐量化：${recommendedQuantization || 'auto'}。如果你更关注低显存稳定性，可优先尝试推荐组合。`}
                  />
                )}

                {comparisonMode ? (
                  <VersionComparisonChat 
                    modelOptions={modelOptions} 
                    currentBackend={currentBackend}
                  />
                ) : (
                  <>
                    <div style={{ marginBottom: 'var(--space-4)' }}>
                      <Select
                        placeholder={currentBackend === 'ollama' ? '选择 Ollama 模型' : '选择模型'}
                        value={selectedModel}
                        onChange={(model) => {
                          setSelectedModel(model);
                          syncInferenceSelection({ backend: currentBackend, modelId: model });
                        }}
                        style={{ width: 250 }}
                        options={modelOptions}
                        disabled={loading}
                        loading={modelOptions.length === 0}
                      />
                    </div>
                    {currentBackend === 'huggingface' && (
                      <div style={{ marginBottom: 'var(--space-4)' }}>
                        <Input
                          value={loraAdapter}
                          onChange={(event) => setLoraAdapter(event.target.value)}
                          placeholder="可选：LoRA Adapter 路径；部署别名会自动解析"
                          disabled={loading}
                        />
                      </div>
                    )}
                    <div className={`${styles.chatBox} ${loading ? styles.generatingGlow : ''}`}>
                      {response || '模型输出将显示在这里...'}
                      {loading && <LoadingOutlined style={{ marginLeft: 8 }} spin />}
                    </div>

                    <TextArea
                      placeholder="输入你的问题..."
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      onPressEnter={(e) => {
                        if (!e.shiftKey) {
                          e.preventDefault();
                          handleSend();
                        }
                      }}
                      rows={4}
                      disabled={loading || !selectedModel}
                      style={{ marginBottom: 'var(--space-4)', borderRadius: 'var(--radius-sm)' }}
                      className="glass-input"
                    />

                    <Space>
                      <Button
                        type="primary"
                        icon={<SendOutlined />}
                        onClick={handleSend}
                        loading={loading}
                        disabled={!selectedModel || !prompt.trim()}
                        style={{ borderRadius: 'var(--radius-sm)' }}
                      >
                        发送
                      </Button>
                      <Button
                        icon={<ClearOutlined />}
                        onClick={handleClear}
                        disabled={loading}
                        style={{ borderRadius: 'var(--radius-sm)' }}
                      >
                        清空
                      </Button>
                      <Tag color="blue" style={{ borderRadius: 'var(--radius-sm)' }}>
                        Shift+Enter 换行
                      </Tag>
                      {getBackendBadge()}
                    </Space>
                  </>
                )}
              </GlassCard>
            </Col>

            <Col xs={24} lg={8}>
              <Space direction="vertical" size={24} style={{ width: '100%' }}>
                <GlassCard>
                  <h3
                    style={{
                      marginTop: 0,
                      marginBottom: 'var(--space-6)',
                      fontSize: 'var(--text-lg)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    推理参数
                  </h3>

                  <div style={{ marginBottom: 'var(--space-6)' }}>
                    <div
                      style={{ marginBottom: 'var(--space-2)', display: 'flex', justifyContent: 'space-between' }}
                    >
                      <span style={{ color: 'var(--text-primary)' }}>最大Token数</span>
                      <Tag color="blue" style={{ borderRadius: 'var(--radius-sm)' }}>
                        {maxTokens}
                      </Tag>
                    </div>
                    <Slider
                      min={128}
                      max={4096}
                      step={128}
                      value={maxTokens}
                      onChange={setMaxTokens}
                      disabled={loading}
                    />
                  </div>

                  <div style={{ marginBottom: 'var(--space-6)' }}>
                    <div
                      style={{ marginBottom: 'var(--space-2)', display: 'flex', justifyContent: 'space-between' }}
                    >
                      <span style={{ color: 'var(--text-primary)' }}>Temperature (创造性)</span>
                      <Tag color="blue" style={{ borderRadius: 'var(--radius-sm)' }}>
                        {temperature}
                      </Tag>
                    </div>
                    <Slider
                      min={0.1}
                      max={2.0}
                      step={0.1}
                      value={temperature}
                      onChange={setTemperature}
                      disabled={loading}
                      marks={{
                        0.1: '精确',
                        0.7: '平衡',
                        2.0: '创意',
                      }}
                    />
                  </div>

                  <Divider style={{ borderColor: 'var(--border-color)' }}>参数说明</Divider>
                  <ul
                    style={{
                      paddingLeft: 'var(--space-5)',
                      color: 'var(--text-secondary)',
                      fontSize: 'var(--text-sm)',
                      margin: 0,
                    }}
                  >
                    <li>
                      <b>Max Tokens:</b> 限制回复的最大长度
                    </li>
                    <li>
                      <b>Temperature:</b> 越高越有创意，越低越精确
                    </li>
                    <li>
                      <b>建议:</b> 问答用 0.3-0.5，创作用 0.7-1.0
                    </li>
                  </ul>
                </GlassCard>

                <GlassCard>
                  <h3
                    style={{
                      marginTop: 0,
                      marginBottom: 'var(--space-4)',
                      fontSize: 'var(--text-lg)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    推理后端
                  </h3>
                  {observed.inference.backends.map((backend) => (
                    <div
                      key={backend.id}
                      className={`${styles.backendItem} ${currentBackend === backend.id ? styles.backendItemActive : ''}`}
                      role="button"
                      tabIndex={backend.available ? 0 : -1}
                      aria-current={currentBackend === backend.id ? 'true' : undefined}
                      aria-disabled={!backend.available}
                      aria-label={`选择推理后端 ${backend.id}`}
                      style={{
                        cursor: backend.available ? 'pointer' : 'not-allowed',
                        opacity: backend.available ? 1 : 0.6,
                      }}
                      onClick={() => backend.available && handleBackendChange(backend.id)}
                      onKeyDown={(e) => {
                        if (backend.available && (e.key === 'Enter' || e.key === ' ')) {
                          e.preventDefault();
                          handleBackendChange(backend.id);
                        }
                      }}
                    >
                      <div
                        style={{
                          fontWeight: currentBackend === backend.id ? 'var(--font-semibold)' : 'var(--font-normal)',
                          color: 'var(--text-primary)',
                        }}
                      >
                        {backend.name}
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                        {backend.description}
                      </div>
                    </div>
                  ))}
                </GlassCard>

                <GlassCard>
                  <h3
                    style={{
                      marginTop: 0,
                      marginBottom: 'var(--space-4)',
                      fontSize: 'var(--text-lg)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    使用提示
                  </h3>
                  <ul
                    style={{
                      paddingLeft: 'var(--space-5)',
                      color: 'var(--text-secondary)',
                      fontSize: 'var(--text-sm)',
                      margin: 0,
                    }}
                  >
                    <li>支持 HuggingFace 本地模型推理</li>
                    <li>也支持 Ollama 部署的模型</li>
                    <li>训练完成后可在推理测试中验证效果</li>
                  </ul>
                </GlassCard>
              </Space>
            </Col>
          </Row>
        </MotionItem>
      )}
    </MotionList>
  );
}
