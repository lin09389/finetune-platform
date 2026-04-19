import {
  ClearOutlined,
  CodeOutlined,
  LoadingOutlined,
  SendOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { Alert, Badge, Button, Col, Divider, Input, Row, Select, Slider, Space, Tag } from 'antd';
import { useEffect, useState } from 'react';
import RuntimeContextPanel from '../components/runtime/RuntimeContextPanel';
import glassStyles from '../components/shared/GlassCard.module.css';
import InsightPanel from '../components/shared/InsightPanel';
import PageHeader from '../components/shared/PageHeader';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { useRuntimeContext } from '../runtime/RuntimeContext';
import {
  getPerformanceRecommendations,
  getPerformanceStats,
  listInferenceEngines,
  streamGenerate,
  streamInference,
  switchBackend,
  type InferenceEngine,
} from '../services/api';
import { notify } from '../utils/notify';
import styles from './Inference.module.css';

const { TextArea } = Input;

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
  const [currentBackend, setCurrentBackend] = useState<string>(
    observed.inference.currentBackend || 'huggingface',
  );
  const [inferenceEngines, setInferenceEngines] = useState<InferenceEngine[]>([]);
  const [performanceStats, setPerformanceStats] = useState<any>(null);
  const [performanceRecommendations, setPerformanceRecommendations] = useState<string[]>([]);

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

  useEffect(() => {
    const loadEngines = async () => {
      try {
        const enginesData = await listInferenceEngines();
        setInferenceEngines(enginesData.engines);
      } catch (e) {
        console.warn('Failed to load inference engines:', e);
      }
    };

    void loadEngines();
  }, []);

  const loadPerformance = async () => {
    try {
      const [stats, recommendations] = await Promise.all([
        getPerformanceStats().catch(() => null),
        getPerformanceRecommendations().catch(() => null),
      ]);
      setPerformanceStats(stats);
      setPerformanceRecommendations(recommendations?.recommendations || []);
    } catch (error) {
      console.error('Failed to load performance info:', error);
    }
  };

  const handleBackendChange = async (backend: string) => {
    try {
      await switchBackend(backend);
      setCurrentBackend(backend);
      setSelectedModel(undefined);
      syncInferenceSelection({ backend, modelId: undefined });
      await refreshInference();
      notify.success(`已切换到 ${backend === 'ollama' ? 'Ollama' : 'HuggingFace'} 后端`);
    } catch (error) {
      notify.error('切换失败');
    }
  };

  const modelOptions =
    currentBackend === 'ollama'
      ? observed.inference.ollamaModels.map((m) => ({ value: m.id, label: m.name }))
      : observed.inference.huggingfaceModels.map((m) => ({
          value: m.id,
          label: m.name,
        }));

  const currentBackendInfo = observed.inference.backends.find((b) => b.id === currentBackend);
  const isBackendAvailable = currentBackendInfo?.available ?? true;

  const handleSend = async () => {
    if (!selectedModel || !prompt.trim()) return;

    setLoading(true);
    setResponse('');

    try {
      if (inferenceEngines.length > 0) {
        await streamGenerate(
          {
            model_id: selectedModel,
            prompt: prompt,
            max_tokens: maxTokens,
            temperature: temperature,
            backend: currentBackend,
          },
          (text: string) => {
            setResponse((prev) => prev + text);
          },
        );
      } else {
        await streamInference(
          {
            modelId: selectedModel,
            prompt: prompt,
            maxTokens: maxTokens,
            temperature: temperature,
            backend: currentBackend,
          },
          (text: string) => {
            setResponse((prev) => prev + text);
          },
        );
      }
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : '推理失败';
      setResponse(`错误: ${errorMsg}`);
    } finally {
      setLoading(false);
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
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
            后端服务未连接，请先启动应用
          </div>
        </MotionItem>
      ) : (
        <MotionItem>
          <Row gutter={[24, 24]}>
            <Col xs={24} lg={16}>
              <div className={`${glassStyles.glassCard} ${styles.card}`}>
                <div style={{ marginBottom: 24 }}>
                  <RuntimeContextPanel page="inference" />
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 24,
                  }}
                >
                  <h3 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)' }}>对话</h3>
                  <Space>
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
                  </Space>
                </div>

                {!isBackendAvailable && currentBackend === 'ollama' && (
                  <Alert
                    type="warning"
                    message="Ollama 未运行"
                    description="请确保 Ollama 已启动，然后刷新页面"
                    showIcon
                    style={{ marginBottom: 16, borderRadius: 8 }}
                    action={
                      <Button size="small" onClick={() => void refreshInference()}>
                        刷新
                      </Button>
                    }
                  />
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
                  style={{ marginBottom: 16, borderRadius: 8 }}
                  className="glass-input"
                />

                <Space>
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    loading={loading}
                    disabled={!selectedModel || !prompt.trim()}
                    style={{ borderRadius: 8 }}
                  >
                    发送
                  </Button>
                  <Button
                    icon={<ClearOutlined />}
                    onClick={handleClear}
                    disabled={loading}
                    style={{ borderRadius: 8 }}
                  >
                    清空
                  </Button>
                  <Tag color="blue" style={{ borderRadius: 4 }}>
                    Shift+Enter 换行
                  </Tag>
                  {getBackendBadge()}
                </Space>
              </div>
            </Col>

            <Col xs={24} lg={8}>
              <Space direction="vertical" size={24} style={{ width: '100%' }}>
                <div className={glassStyles.glassCard}>
                  <h3
                    style={{
                      marginTop: 0,
                      marginBottom: 24,
                      fontSize: 18,
                      color: 'var(--text-primary)',
                    }}
                  >
                    推理参数
                  </h3>

                  <div style={{ marginBottom: 24 }}>
                    <div
                      style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}
                    >
                      <span style={{ color: 'var(--text-primary)' }}>最大Token数</span>
                      <Tag color="blue" style={{ borderRadius: 4 }}>
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

                  <div style={{ marginBottom: 24 }}>
                    <div
                      style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}
                    >
                      <span style={{ color: 'var(--text-primary)' }}>Temperature (创造性)</span>
                      <Tag color="blue" style={{ borderRadius: 4 }}>
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
                      paddingLeft: 20,
                      color: 'var(--text-secondary)',
                      fontSize: 13,
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
                </div>

                <div className={glassStyles.glassCard}>
                  <h3
                    style={{
                      marginTop: 0,
                      marginBottom: 16,
                      fontSize: 18,
                      color: 'var(--text-primary)',
                    }}
                  >
                    推理后端
                  </h3>
                  {observed.inference.backends.map((backend) => (
                    <div
                      key={backend.id}
                      className={`${styles.backendItem} ${currentBackend === backend.id ? styles.backendItemActive : ''}`}
                      style={{
                        cursor: backend.available ? 'pointer' : 'not-allowed',
                        opacity: backend.available ? 1 : 0.6,
                      }}
                      onClick={() => backend.available && handleBackendChange(backend.id)}
                    >
                      <div
                        style={{
                          fontWeight: currentBackend === backend.id ? 600 : 400,
                          color: 'var(--text-primary)',
                        }}
                      >
                        {backend.name}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {backend.description}
                      </div>
                    </div>
                  ))}
                </div>

                <div className={glassStyles.glassCard}>
                  <InsightPanel
                    embedded
                    title="运行观测"
                    status={{
                      type: performanceStats?.inference?.total_requests > 0 ? 'info' : 'pending',
                      text: performanceStats?.inference?.total_requests > 0 ? '已采样' : '等待样本',
                    }}
                    summary="这组指标用于判断当前推理链路是否健康，尤其适合在切换后端、模型预热或做性能回归时快速确认变化。"
                    metrics={[
                      {
                        label: '已记录推理次数',
                        value: performanceStats?.inference?.total_requests ?? 0,
                      },
                      {
                        label: '平均首响应 / 总耗时',
                        value: `${performanceStats?.streaming?.avg_first_token_ms ?? 0} ms / ${performanceStats?.inference?.avg_latency_ms ?? 0} ms`,
                      },
                    ]}
                    sections={[
                      {
                        title: '性能建议',
                        items: performanceRecommendations.slice(0, 3),
                      },
                    ]}
                    footer={
                      performanceRecommendations.length > 0
                        ? undefined
                        : '暂无性能建议，先运行几次推理即可生成观测数据。'
                    }
                  />
                </div>

                <div className={glassStyles.glassCard}>
                  <h3
                    style={{
                      marginTop: 0,
                      marginBottom: 16,
                      fontSize: 18,
                      color: 'var(--text-primary)',
                    }}
                  >
                    使用提示
                  </h3>
                  <ul
                    style={{
                      paddingLeft: 20,
                      color: 'var(--text-secondary)',
                      fontSize: 13,
                      margin: 0,
                    }}
                  >
                    <li>支持 HuggingFace 本地模型推理</li>
                    <li>也支持 Ollama 部署的模型</li>
                    <li>训练完成后可在推理测试中验证效果</li>
                  </ul>
                </div>
              </Space>
            </Col>
          </Row>
        </MotionItem>
      )}
    </MotionList>
  );
}
