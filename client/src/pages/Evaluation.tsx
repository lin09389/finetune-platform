import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  FileSearchOutlined,
  LikeOutlined,
  DislikeOutlined,
  MinusCircleOutlined,
  PlusOutlined,
  ClockCircleOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import {
  Alert, AutoComplete, Button, Col, Collapse, Descriptions, Divider, Form, Input,
  InputNumber, Row, Select, Space, Switch, Tag, message, Progress,
  Typography, Drawer, Segmented, Spin, Tooltip
} from 'antd';
import { useEffect, useMemo, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import PageHeader from '../components/shared/PageHeader';
import GlassCard from '../components/shared/GlassCard';
import { MotionList, MotionItem, CountUp, MotionCard, MotionButton, FadeInSection } from '../components/shared/MotionWrapper';
import StatusBadge, { StatusType } from '../components/shared/StatusBadge';
import EmptyState from '../components/shared/EmptyState';
import styles from './Evaluation.module.css';
import {
  createEvaluationRun, getDatasetList, getInferenceModels, getModelList,
  scoreEvaluationCase, getEvaluationRun, getEvaluationRuns
} from '../services/api';
import { useAppStore } from '../store/appStore';
import type { AppTaskGoal, DatasetInfo, EvaluationRun, ModelInfo } from '../types';
import JSONDataEditor from '../components/shared/JSONDataEditor';

const { Text } = Typography;

const scenarioOptions = [
  { label: '客服/知识问答助手', value: 'qa_assistant' },
  { label: '结构化输出/信息抽取', value: 'structured_extraction' },
];

const getScenarioLabel = (scenario?: string) =>
  scenarioOptions.find((item) => item.value === scenario)?.label || scenario || '-';

const metricLabels: Record<string, string> = {
  json_valid_rate: 'JSON 合法率',
  schema_match_rate: 'Schema 符合率',
  field_completeness_rate: '字段完整率',
  human_score_count: '人工评分数',
  good_rate: '好评率',
  coverage_marked_count: '覆盖度标记数',
  grounding_marked_count: '依据上下文标记数',
};

type SelectOption = { label: string; value: string; backend?: string };

const getStringValue = (item: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const value = item[key];
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return '';
};

const normalizeModelOptions = (items: unknown[]): SelectOption[] => {
  const optionMap = new Map<string, SelectOption>();

  for (const item of items) {
    let value = '';
    let label = '';
    let tag = '';
    let backend = '';

    if (typeof item === 'string') {
      value = item;
      label = item;
    } else if (item && typeof item === 'object') {
      const record = item as Record<string, unknown>;
      value = getStringValue(record, ['id', 'model_id', 'name', 'model_name', 'path']);
      label = getStringValue(record, ['name', 'model_name', 'id', 'model_id', 'path']);
      tag = getStringValue(record, ['backend', 'source', 'type']);
      backend = getStringValue(record, ['backend']);
    }

    if (!value) continue;

    if (optionMap.has(value)) {
        const existing = optionMap.get(value)!;
        if (!existing.backend && backend) existing.backend = backend;
    } else {
        optionMap.set(value, {
            value,
            label: tag ? `${label || value} · ${tag}` : label || value,
            backend: backend || (typeof item === 'object' && item && 'type' in item ? 'huggingface' : undefined),
        });
    }
  }

  return Array.from(optionMap.values()).sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
};

const normalizeDatasetOptions = (items: unknown[]): SelectOption[] => {
  return items
    .filter((item): item is DatasetInfo => {
      if (!item || typeof item !== 'object') return false;
      return typeof (item as DatasetInfo).id === 'string' && Boolean((item as DatasetInfo).id);
    })
    .map((item) => ({
      value: item.id,
      label: `${item.name || item.id}${item.samples ? ` · ${item.samples} 条` : ''}`,
    }))
    .filter((item) => item.value);
};

export default function Evaluation() {
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { models, datasets, trainingRecords, setModels, setDatasets, backendStatus } = useAppStore();
  const [historyRuns, setHistoryRuns] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [pollingRunId, setPollingRunId] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);
  const [selectorLoading, setSelectorLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [allModelOptions, setAllModelOptions] = useState<SelectOption[]>(() =>
    normalizeModelOptions(models),
  );
  const [datasetOptions, setDatasetOptions] = useState<SelectOption[]>(() =>
    normalizeDatasetOptions(datasets),
  );
  const adapterOptions = useMemo<SelectOption[]>(() =>
    trainingRecords
      .filter(r => r.status === 'completed' && r.adapterPath)
      .map(r => ({ label: `${r.modelName} - ${r.id}`, value: r.adapterPath! })),
    [trainingRecords],
  );
  const modelOptionByValue = useMemo(
    () => new Map(allModelOptions.map((option) => [option.value, option])),
    [allModelOptions],
  );

  const watchedBackend = Form.useWatch('backend', form) as string | undefined;
  const modelOptions = useMemo(() => {
    if (watchedBackend === 'ollama') {
      return allModelOptions.filter((option) => option.backend === 'ollama');
    }
    if (watchedBackend === 'huggingface') {
      return allModelOptions.filter(
        (option) => option.backend === 'huggingface' || option.backend === 'llama-cpp',
      );
    }
    return allModelOptions;
  }, [allModelOptions, watchedBackend]);

  const initialDatasetId = searchParams.get('test_dataset_id');
  const [testMode, setTestMode] = useState<'dataset' | 'single'>(initialDatasetId ? 'dataset' : 'single');

  const watchedScenario = Form.useWatch('scenario', form) as AppTaskGoal | undefined;
  const watchedBaseModel = Form.useWatch('base_model', form) as string | undefined;
  const watchedFinetunedModel = Form.useWatch('finetuned_model', form) as string | undefined;
  const watchedAdapterPath = Form.useWatch('adapter_path', form) as string | undefined;
  const watchedTrainingTaskId = Form.useWatch('training_task_id', form) as string | undefined;
  const watchedAutoMergeAdapter = Form.useWatch('auto_merge_adapter', form) as boolean | undefined;

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const runs = await getEvaluationRuns();
      setHistoryRuns(runs || []);
    } catch (err) {
      console.error('Failed to load history', err);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    const values: Record<string, string | number | boolean> = {};
    const stringKeys = [
      'scenario',
      'base_model',
      'finetuned_model',
      'adapter_path',
      'backend',
      'test_dataset_id',
      'training_task_id',
    ];
    const numberKeys = ['max_tokens', 'temperature', 'max_cases'];

    let hasParams = false;
    stringKeys.forEach((key) => {
      const value = searchParams.get(key);
      if (value) {
        values[key] = value;
        hasParams = true;
      }
    });

    numberKeys.forEach((key) => {
      const value = searchParams.get(key);
      if (!value) return;
      const numeric = Number(value);
      if (Number.isFinite(numeric)) {
        values[key] = numeric;
        hasParams = true;
      }
    });

    const runInference = searchParams.get('run_inference');
    if (runInference !== null) {
      values.run_inference = runInference !== 'false';
      hasParams = true;
    }
    const autoMergeAdapter = searchParams.get('auto_merge_adapter');
    if (autoMergeAdapter !== null) {
      values.auto_merge_adapter = autoMergeAdapter !== 'false';
      hasParams = true;
    }

    if (Object.keys(values).length) {
      form.setFieldsValue(values);
      if (values.test_dataset_id) {
        setTestMode('dataset');
      }
    }

    // Auto-open drawer if coming with parameters
    if (hasParams && !run) {
      setDrawerOpen(true);
      setSearchParams({}); // Clear params to avoid re-triggering
    }
  }, [form, searchParams, run, setSearchParams]);

  useEffect(() => {
    if (backendStatus !== 'connected') return;

    const loadSelectors = async () => {
      setSelectorLoading(true);
      try {
        const [modelResult, inferenceModelResult, datasetResult] = await Promise.allSettled([
          getModelList(),
          getInferenceModels(),
          getDatasetList(),
        ]);

        const modelItems: unknown[] = [];
        if (modelResult.status === 'fulfilled' && Array.isArray(modelResult.value)) {
          modelItems.push(...modelResult.value);
          setModels(modelResult.value as ModelInfo[]);
        }
        if (
          inferenceModelResult.status === 'fulfilled' &&
          Array.isArray(inferenceModelResult.value)
        ) {
          modelItems.push(...inferenceModelResult.value);
        }
        if (modelItems.length) {
          setAllModelOptions(normalizeModelOptions(modelItems));
        }

        if (datasetResult.status === 'fulfilled' && Array.isArray(datasetResult.value)) {
          setDatasets(datasetResult.value as DatasetInfo[]);
          setDatasetOptions(normalizeDatasetOptions(datasetResult.value));
        }
      } catch {
        message.warning('模型或数据集列表加载失败，可先手动输入模型路径');
      } finally {
        setSelectorLoading(false);
      }
    };

    void loadSelectors();
  }, [backendStatus, setDatasets, setModels]);

  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        window.clearTimeout(pollingRef.current);
      }
    };
  }, []);

  const selectHistoryRun = async (runId: string) => {
    if (pollingRunId === runId) return; // Already polling this
    setLoading(true);
    setRun(null);
    if (pollingRef.current) {
        window.clearTimeout(pollingRef.current);
        setPollingRunId(null);
    }
    try {
      const data = await getEvaluationRun(runId);
      setRun(data);
      if (data.status === 'pending' || data.status === 'running') {
        setPollingRunId(runId);
        pollEvaluationStatus(runId);
      } else {
        setLoading(false);
      }
    } catch (err) {
      message.error('加载评估报告失败');
      setLoading(false);
    }
  };

  const pollEvaluationStatus = async (runId: string) => {
    try {
      const data = await getEvaluationRun(runId);
      setRun(data);
      if (data.status === 'pending' || data.status === 'running') {
        pollingRef.current = window.setTimeout(() => pollEvaluationStatus(runId), 2000);
      } else {
        setPollingRunId(null);
        setLoading(false);
        loadHistory();
        if (data.status === 'completed' || data.status === 'completed_with_warnings') {
          message.success('评估完成');
        } else {
          message.error(`评估失败: ${data.error || '未知错误'}`);
        }
      }
    } catch (error) {
      console.error('Polling error:', error);
      pollingRef.current = window.setTimeout(() => pollEvaluationStatus(runId), 2000);
    }
  };

  const handleCreateRun = async (values: any) => {
    setLoading(true);
    try {
      const selectedBackend = values.backend || 'ollama';
      const ensureModelMatchesBackend = (fieldLabel: string, modelValue?: string) => {
        if (!modelValue) return;

        const knownOption = modelOptionByValue.get(modelValue);
        if (selectedBackend === 'ollama') {
          if (knownOption?.backend && knownOption.backend !== 'ollama') {
            throw new Error(`${fieldLabel}“${modelValue}”不属于 Ollama 模型，请切换到 HuggingFace 后端或改选 Ollama tag。`);
          }
          if (/[\\/]/.test(modelValue)) {
            throw new Error(`${fieldLabel}“${modelValue}”看起来是本地路径。Ollama 后端需要类似 \`qwen2.5:7b\` 的模型 tag。`);
          }
        }

        if (
          selectedBackend === 'huggingface' &&
          knownOption?.backend &&
          knownOption.backend !== 'huggingface' &&
          knownOption.backend !== 'llama-cpp'
        ) {
          throw new Error(`${fieldLabel}“${modelValue}”不是本地 HuggingFace 模型，请切换到 Ollama 后端或改选本地模型目录。`);
        }
      };

      ensureModelMatchesBackend('基础模型', values.base_model);
      ensureModelMatchesBackend('微调模型', values.finetuned_model);

      const schema = values.schema ? (typeof values.schema === 'string' ? JSON.parse(values.schema) : values.schema) : undefined;
      const isDatasetMode = testMode === 'dataset';
      const payload = {
        scenario: values.scenario,
        base_model: values.base_model,
        finetuned_model: values.finetuned_model,
        adapter_path: values.adapter_path,
        backend: values.backend || 'ollama',
        run_inference: values.run_inference ?? true,
        auto_merge_adapter: values.auto_merge_adapter ?? true,
        max_tokens: values.max_tokens ?? 512,
        temperature: values.temperature ?? 0.2,
        max_cases: values.max_cases ?? 20,
        test_dataset_id: isDatasetMode ? values.test_dataset_id : undefined,
        cases: (!isDatasetMode && values.prompt)
          ? [
              {
                prompt: values.prompt,
                expected_output: values.expected_output,
                schema,
                base_output: values.base_output,
                finetuned_output: values.finetuned_output,
              },
            ]
          : [],
      };
      const response = await createEvaluationRun(payload);
      setRun(response);
      setDrawerOpen(false); // Close drawer after creation
      loadHistory(); // refresh history

      if (response.status === 'pending' || response.status === 'running') {
        setPollingRunId(response.run_id);
        pollEvaluationStatus(response.run_id);
      } else {
        setLoading(false);
      }
    } catch (error: any) {
      setLoading(false);
      message.error(error?.message || '创建评估失败，请检查 JSON schema');
    }
  };

  const handleScore = async (caseIndex: number, score: 'good' | 'neutral' | 'bad') => {
    if (!run) return;
    const nextRun = await scoreEvaluationCase(run.run_id, { case_index: caseIndex, score });
    setRun(nextRun);
  };

  const openDeployment = () => {
    const adapterPath = run?.adapter_merge?.adapter_path || run?.adapter_path || watchedAdapterPath || '';
    const mergedModelPath =
      run?.adapter_merge?.merged_model_path || run?.finetuned_model || watchedFinetunedModel || '';
    const baseModel = run?.base_model || watchedBaseModel || '';
    const trainingTaskId = watchedTrainingTaskId || run?.run_id || '';

    if (!baseModel) {
      message.warning('缺少基础模型，暂时无法生成部署包');
      return;
    }
    if (!adapterPath) {
      message.warning('缺少 Adapter 路径，暂时无法生成部署包');
      return;
    }

    const params = new URLSearchParams();
    params.set('training_task_id', trainingTaskId || 'manual-evaluation');
    params.set('base_model', baseModel);
    params.set('adapter_path', adapterPath);
    if (mergedModelPath) params.set('merged_model_path', mergedModelPath);
    params.set(
      'model_alias',
      (run?.scenario || watchedScenario) === 'qa_assistant' ? 'qa-assistant-finetuned' : 'structured-extraction-finetuned',
    );

    navigate(`/deployment?${params.toString()}`);
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success('已复制到剪贴板');
  };

  const renderCopyableTextBlock = (title: string, subtitle: string, text: string, type: 'neutral' | 'accent' | 'error') => (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <span style={{ fontWeight: 500, color: 'var(--text-secondary)' }}>{title}</span>
          {subtitle && <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal', color: 'var(--text-tertiary)', marginLeft: 8 }} ellipsis>{subtitle}</Text>}
        </div>
        <Tooltip title="复制代码">
          <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => handleCopy(text)} style={{ color: 'var(--text-tertiary)' }} />
        </Tooltip>
      </div>
      <div style={{
        flex: 1, padding: '12px 16px', borderRadius: 8, whiteSpace: 'pre-wrap',
        fontFamily: 'var(--font-mono)', fontSize: 13, color: type === 'error' ? 'var(--error)' : 'var(--text-primary)',
        background: type === 'accent' ? 'rgba(0, 255, 194, 0.04)' : type === 'error' ? 'rgba(255, 77, 79, 0.04)' : 'rgba(0, 0, 0, 0.3)',
        border: type === 'accent' ? '1px solid rgba(0, 255, 194, 0.2)' : type === 'error' ? '1px solid rgba(255, 77, 79, 0.2)' : '1px solid rgba(255, 255, 255, 0.08)'
      }}>
        {text}
      </div>
    </div>
  );

  const metricEntries = Object.entries(run?.metrics ?? {});

  return (
    <div style={{ padding: 24, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader
        title="评估实验室"
        icon={<FileSearchOutlined />}
        helpTooltip="对比基础模型和微调模型在问答、结构化抽取场景下的输出效果。"
        extraActions={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>
                新建评估
            </Button>
        }
      />

      <Row gutter={[24, 24]} style={{ flex: 1, minHeight: 0 }}>
        {/* Left Sidebar: History List */}
        <Col xs={24} lg={7} style={{ height: '100%' }}>
            <GlassCard style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
                <div style={{ padding: '16px 24px', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ClockCircleOutlined style={{ color: 'var(--text-secondary)' }} />
                    <span style={{ fontWeight: 500 }}>评估历史</span>
                </div>
                <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
                    <Spin spinning={historyLoading}>
                        {historyRuns.length > 0 ? (
                            <MotionList>
                                {historyRuns.map((item) => {
                                    const isSelected = run?.run_id === item.run_id;
                                    let statusType: StatusType = 'info';
                                    if (item.status === 'completed' || item.status === 'completed_with_warnings') statusType = 'success';
                                    else if (item.status === 'failed') statusType = 'error';
                                    else if (item.status === 'running' || item.status === 'pending') statusType = 'processing';

                                    return (
                                        <MotionItem key={item.run_id}>
                                            <div
                                                onClick={() => selectHistoryRun(item.run_id)}
                                                style={{
                                                    padding: '16px 20px',
                                                    cursor: 'pointer',
                                                    borderRadius: 12,
                                                    marginBottom: 8,
                                                    transition: 'all 0.3s ease',
                                                    borderLeft: isSelected ? '4px solid var(--accent-primary)' : '4px solid transparent',
                                                    background: isSelected ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.01)',
                                                    border: isSelected ? '1px solid rgba(255,255,255,0.1)' : '1px solid transparent',
                                                }}
                                                className={styles.historyItemHover}
                                            >
                                                <div style={{ width: '100%' }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                                                        <Text style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 14 }} ellipsis>{item.base_model}</Text>
                                                        <StatusBadge status={statusType} text={item.status === 'completed_with_warnings' ? 'completed' : item.status} size="small" />
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-tertiary)' }}>
                                                        <span style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: 4 }}>{getScenarioLabel(item.scenario)}</span>
                                                        <span>{new Date(item.created_at).toLocaleString('zh-CN', {month:'numeric', day:'numeric', hour:'numeric', minute:'numeric'})}</span>
                                                    </div>
                                                    {(item.status === 'running' || item.status === 'pending') && (
                                                        <Progress percent={99} status="active" showInfo={false} size="small" strokeColor="var(--accent-primary)" style={{ marginTop: 8, marginBottom: 0 }} />
                                                    )}
                                                </div>
                                            </div>
                                        </MotionItem>
                                    );
                                })}
                            </MotionList>
                        ) : (
                            <EmptyState
                                description="暂无评估历史，点击右上角开始您的第一次测试吧"
                                style={{ margin: '40px 0' }}
                            />
                        )}
                    </Spin>
                </div>
            </GlassCard>
        </Col>

        {/* Right Main Content: Result View */}
        <Col xs={24} lg={17} style={{ height: '100%' }}>
          <div style={{ height: '100%', overflowY: 'auto', paddingRight: 8 }}>
            {run ? (
              <FadeInSection>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24, paddingBottom: 24 }}>
                <MotionCard className={styles.evaluationCard} style={{ padding: 24 }}>
                  <div className={styles.neonStripe} style={{ '--stripe-color': 'var(--accent-neon-green, #00FFC2)' } as React.CSSProperties} />
                  <div className={styles.cardTitle} style={{ justifyContent: 'space-between', marginBottom: 20 }}>
                    <Space>
                      <CheckCircleOutlined style={{ color: 'var(--accent-neon-green, #00FFC2)', fontSize: 20 }} />
                      <span style={{ fontSize: 18, fontWeight: 600 }}>{run.run_id}</span>
                      <Tag color="blue" style={{ marginLeft: 8 }}>{getScenarioLabel(run.scenario)}</Tag>
                    {run.status === 'completed' && run.adapter_merge && (
                      <MotionButton>
                        <Button icon={<CloudUploadOutlined />} onClick={openDeployment} style={{ background: 'var(--glass-bg)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}>
                            部署到测试环境
                        </Button>
                      </MotionButton>
                    )}</Space>
                  </div>

                  <Descriptions
                    size="small"
                    column={{ xs: 1, sm: 2, lg: 3 }}
                    styles={{
                        label: { color: 'var(--text-secondary)', width: 96 },
                        content: { wordBreak: 'break-all', color: 'var(--text-primary)' },
                    }}
                  >
                    <Descriptions.Item label="基础模型"><Text strong>{run.base_model}</Text></Descriptions.Item>
                    <Descriptions.Item label="测试数据">{run.test_dataset_id || '单条提示词'}</Descriptions.Item>
                    <Descriptions.Item label="后端推理">{run.backend}</Descriptions.Item>
                    <Descriptions.Item label="微调模型"><Text strong>{run.finetuned_model || '-'}</Text></Descriptions.Item>
                    <Descriptions.Item label="Adapter">{run.adapter_path || '-'}</Descriptions.Item>
                    <Descriptions.Item label="自动合并">{run.adapter_merge ? '是' : '否'}</Descriptions.Item>
                  </Descriptions>

                  {(run.status === 'pending' || run.status === 'running') && (
                    <div style={{ textAlign: 'center', padding: '40px 0', background: 'rgba(0,0,0,0.1)', borderRadius: 12, marginTop: 16 }}>
                      <Progress
                        type="circle"
                        percent={(() => {
                            if (!run?.cases?.length) return 0;
                            const hasFinetuned = !!(run.finetuned_model || run.adapter_path || run.adapter_merge);
                            const total = run.cases.length * (hasFinetuned ? 2 : 1);
                            const completedBase = run.cases.filter((c: any) => c.base_output || c.base_output_error).length;
                            const completedFinetuned = hasFinetuned ? run.cases.filter((c: any) => c.finetuned_output || c.finetuned_output_error).length : 0;
                            return Math.round(((completedBase + completedFinetuned) / total) * 100);
                        })()}
                        status="active"
                        strokeColor="var(--accent-primary)"
                      />
                      <div style={{ marginTop: 16, color: 'var(--text-secondary)' }}>
                        模型正在进行推理，可能需要几分钟时间，请耐心等待...
                      </div>
                    </div>
                  )}

                  {run.warnings?.length ? (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginTop: 16, background: 'rgba(250, 173, 20, 0.1)', border: '1px solid rgba(250, 173, 20, 0.3)' }}
                      message="评估过程中有提示"
                      description={run.warnings.join('；')}
                    />
                  ) : null}
                </MotionCard>

                {/* Metrics */}
                {(run.status === 'completed' || run.status === 'completed_with_warnings') && metricEntries.length > 0 && (
                    <Row gutter={[16, 16]}>
                    {metricEntries.map(([key, value]) => {
                        const isPercentage = ['json_valid_rate', 'schema_match_rate', 'field_completeness_rate', 'good_rate'].includes(key);
                        return (
                            <Col xs={12} md={8} key={key}>
                                <MotionCard className={styles.evaluationCard} style={{ padding: '16px 24px', display: 'flex', alignItems: 'center', gap: 20 }}>
                                    <div className={styles.neonStripe} style={{ '--stripe-color': 'var(--accent-neon-purple, #9D00FF)' } as React.CSSProperties} />
                                    {isPercentage && typeof value === 'number' ? (
                                        <Progress
                                            type="circle"
                                            percent={Number((value * 100).toFixed(1))}
                                            size={64}
                                            strokeColor="var(--accent-neon-purple)"
                                            trailColor="rgba(255,255,255,0.05)"
                                        />
                                    ) : null}
                                    <div style={{ flex: 1 }}>
                                        <div style={{ color: 'var(--text-secondary)', marginBottom: 8, fontSize: 14 }}>{metricLabels[key] || key}</div>
                                        {isPercentage ? null : (
                                            <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                                                <CountUp value={Number(value) || 0} />
                                            </div>
                                        )}
                                    </div>
                                </MotionCard>
                            </Col>
                        );
                    })}
                    </Row>
                )}

                {/* Test Cases */}
                {(run.status === 'completed' || run.status === 'completed_with_warnings') && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      {run.cases?.map((record: any, index: number) => (
                        <MotionCard
                          key={index}
                          className={styles.evaluationCard}
                          style={{ padding: '24px', background: 'var(--bg-elevated)', border: '1px solid rgba(255, 255, 255, 0.05)' }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div style={{ background: 'rgba(255,255,255,0.1)', width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>
                                    {index + 1}
                                </div>
                                <Text style={{ color: 'var(--text-primary)', fontSize: 16, fontWeight: 500 }}>评估样本</Text>
                            </div>
                            <Space size={8}>
                              <MotionButton onClick={() => handleScore(index, 'good')}>
                                <Button
                                  size="small"
                                  type={record.human_score?.score === 'good' ? 'primary' : 'default'}
                                  icon={<LikeOutlined />}
                                  style={record.human_score?.score === 'good' ? undefined : { background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)', border: 'none' }}
                                >
                                  好
                                </Button>
                              </MotionButton>
                              <MotionButton onClick={() => handleScore(index, 'neutral')}>
                                <Button
                                  size="small"
                                  type={record.human_score?.score === 'neutral' ? 'primary' : 'default'}
                                  icon={<MinusCircleOutlined />}
                                  style={record.human_score?.score === 'neutral' ? undefined : { background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)', border: 'none' }}
                                >
                                  一般
                                </Button>
                              </MotionButton>
                              <MotionButton onClick={() => handleScore(index, 'bad')}>
                                <Button
                                  size="small"
                                  danger={record.human_score?.score === 'bad'}
                                  type={record.human_score?.score === 'bad' ? 'primary' : 'default'}
                                  icon={<DislikeOutlined />}
                                  style={record.human_score?.score === 'bad' ? undefined : { background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)', border: 'none' }}
                                >
                                  差
                                </Button>
                              </MotionButton>
                            </Space>
                          </div>
                          <div style={{ marginBottom: 20 }}>
                            {renderCopyableTextBlock('提示词 (Prompt)', '', String(record.prompt || ''), 'neutral')}
                          </div>

                          <Row gutter={20} style={{ display: 'flex', alignItems: 'stretch' }}>
                            <Col span={12}>
                                {renderCopyableTextBlock('基础模型输出', run.base_model, String(record.base_output_error || record.base_output || ''), record.base_output_error ? 'error' : 'neutral')}
                            </Col>
                            <Col span={12}>
                                {renderCopyableTextBlock('微调模型输出', String(run.finetuned_model || run.adapter_path || ''), String(record.finetuned_output_error || record.finetuned_output || ''), record.finetuned_output_error ? 'error' : 'accent')}
                            </Col>
                          </Row>
                        </MotionCard>
                      ))}
                    </div>
                )}
              </div>
              </FadeInSection>
            ) : (
                <EmptyState
                    description="请在左侧选择一次评估记录，或点击右上角“新建评估”开启测试"
                    style={{ marginTop: 120 }}
                />
            )}
          </div>
        </Col>
      </Row>

      {/* Drawer for New Evaluation Form */}
      <Drawer
        title={<span style={{ fontSize: 18, fontWeight: 600 }}>新建评估任务</span>}
        width={650}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        maskClosable={pollingRunId === null}
        footer={
            <div style={{ textAlign: 'right', padding: '8px 0' }}>
                <Button onClick={() => setDrawerOpen(false)} style={{ marginRight: 12 }} disabled={pollingRunId !== null} size="large">
                    取消
                </Button>
                <Button type="primary" onClick={() => form.submit()} loading={loading} disabled={pollingRunId !== null} size="large">
                    开始评估
                </Button>
            </div>
        }
      >
        <Form
            form={form}
            layout="vertical"
            initialValues={{
                scenario: 'structured_extraction',
                backend: 'ollama',
                run_inference: true,
                auto_merge_adapter: true,
                max_tokens: 512,
                temperature: 0.2,
                max_cases: 20,
            }}
            onFinish={handleCreateRun}
        >
            <div style={{ fontWeight: 600, marginBottom: 20, fontSize: 16, color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 24, height: 24, background: 'var(--accent-primary)', color: 'var(--text-inverse)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>1</div>
                模型与场景配置
            </div>
            <Form.Item name="scenario" label="应用目标" rules={[{ required: true }]}>
                <Select options={scenarioOptions} size="large" />
            </Form.Item>
            <Row gutter={16}>
                <Col span={12}>
                    <Form.Item name="backend" label="推理后端">
                    <Select
                        size="large"
                        options={[
                        { label: 'Ollama', value: 'ollama' },
                        { label: 'HuggingFace', value: 'huggingface' },
                        { label: 'Llama.cpp', value: 'llama-cpp' },
                        ]}
                    />
                    </Form.Item>
                </Col>
            </Row>
            <Form.Item name="base_model" label={<span style={{ fontWeight: 500 }}>基础模型</span>} rules={[{ required: true }]}>
                <AutoComplete
                options={modelOptions}
                size="large"
                placeholder={watchedBackend === 'huggingface' ? '选择本地模型目录或名称' : '选择模型，或输入 qwen2.5:7b'}
                filterOption={(input, option) =>
                    String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                    String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                }
                notFoundContent={selectorLoading ? '正在加载模型...' : '暂无可选模型'}
                />
            </Form.Item>
            <Form.Item name="finetuned_model" label={<span style={{ fontWeight: 500 }}>微调模型</span>}>
                <AutoComplete
                options={modelOptions}
                size="large"
                placeholder={watchedBackend === 'huggingface' ? '选择已合并模型目录，或输入本地路径' : '选择 Ollama 模型 tag'}
                filterOption={(input, option) =>
                    String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                    String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                }
                allowClear
                />
            </Form.Item>

            <Form.Item name="adapter_path" label={<span style={{ fontWeight: 500 }}>Adapter 路径</span>} rules={[
                {
                validator: async (_, value) => {
                    if (watchedAutoMergeAdapter && !value && watchedFinetunedModel === undefined) {
                    return Promise.reject(new Error('开启自动合并时必须填写 Adapter 路径'));
                    }
                    return Promise.resolve();
                }
                }
            ]}>
                <AutoComplete
                options={adapterOptions}
                size="large"
                placeholder="选择历史训练的 Adapter，或输入绝对路径"
                filterOption={(input, option) =>
                    String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                    String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                }
                />
            </Form.Item>

            <Divider style={{ margin: '32px 0', borderColor: 'var(--border-color)' }} />

            <div style={{ fontWeight: 600, marginBottom: 20, fontSize: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--accent-primary)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 24, height: 24, background: 'var(--accent-primary)', color: 'var(--text-inverse)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>2</div>
                    测试内容
                </div>
                <Segmented
                    options={[{label: '数据集测试', value: 'dataset'}, {label: '单条测试', value: 'single'}]}
                    value={testMode}
                    onChange={(val) => setTestMode(val as 'dataset' | 'single')}
                />
            </div>

            <div style={{ background: 'var(--bg-elevated)', padding: 20, borderRadius: 12, border: '1px solid rgba(255,255,255,0.05)' }}>
                {testMode === 'dataset' ? (
                    <div>
                        <Form.Item name="test_dataset_id" label="测试数据集" rules={[{ required: true }]}>
                        <Select
                            options={datasetOptions}
                            size="large"
                            placeholder="选择已上传数据集批量评估"
                            loading={selectorLoading}
                            showSearch
                            allowClear
                            optionFilterProp="label"
                            notFoundContent={selectorLoading ? '正在加载数据集...' : '暂无数据集'}
                        />
                        </Form.Item>
                        <Form.Item name="max_cases" label="最大抽取样本数" style={{ marginBottom: 0 }}>
                        <InputNumber min={1} max={100} style={{ width: '100%' }} size="large" />
                        </Form.Item>
                    </div>
                ) : (
                    <div>
                        <Form.Item name="prompt" label="测试提示词" rules={[{ required: true }]}>
                        <Input.TextArea rows={4} placeholder="输入单条测试提示词" />
                        </Form.Item>
                        <Collapse
                        ghost
                        style={{ padding: 0, marginLeft: -16, marginBottom: 0 }}
                        items={[
                            {
                            key: 'manual-output',
                            label: <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>进阶：手动填入模型输出 (跳过推理环节)</span>,
                            children: (
                                <>
                                <Form.Item name="base_output" label="基础模型输出" style={{ marginBottom: 12 }}>
                                    <Input.TextArea rows={3} placeholder="可选" />
                                </Form.Item>
                                <Form.Item name="finetuned_output" label="微调模型输出" style={{ marginBottom: 0 }}>
                                    <Input.TextArea rows={3} placeholder="可选" />
                                </Form.Item>
                                </>
                            ),
                            },
                        ]}
                        />
                    </div>
                )}
            </div>

            {watchedScenario === 'structured_extraction' && (
                <Form.Item name="schema" label={<span style={{ fontWeight: 500 }}>JSON Schema / 字段定义</span>} style={{ marginTop: 24 }}>
                    <div style={{ height: 200, border: '1px solid var(--border-color)', borderRadius: 8, overflow: 'hidden' }}>
                    <Form.Item name="schema" noStyle>
                        <JSONDataEditor readOnly={false} height="100%" />
                    </Form.Item>
                    </div>
                </Form.Item>
            )}

            <Divider style={{ margin: '32px 0', borderColor: 'var(--border-color)' }} />

            <Collapse
            ghost
            style={{ padding: 0, marginLeft: -16 }}
            items={[
                {
                key: 'advanced',
                label: <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 24, height: 24, background: 'rgba(255,255,255,0.1)', color: 'var(--text-secondary)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>3</div>
                    高级设置
                </span>,
                children: (
                    <div style={{ paddingTop: 16, paddingLeft: 16 }}>
                    <Row gutter={24}>
                        <Col span={12}>
                        <Form.Item name="temperature" label="温度 (Temperature)">
                            <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} size="large" />
                        </Form.Item>
                        </Col>
                        <Col span={12}>
                        <Form.Item name="max_tokens" label="最大 Token数">
                            <InputNumber min={1} max={4096} style={{ width: '100%' }} size="large" />
                        </Form.Item>
                        </Col>
                        <Col span={12}>
                        <Form.Item name="run_inference" label="自动调用推理" valuePropName="checked">
                            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                        </Form.Item>
                        </Col>
                        <Col span={12}>
                        <Form.Item name="auto_merge_adapter" label="自动合并 Adapter" valuePropName="checked">
                            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                        </Form.Item>
                        </Col>
                    </Row>
                    </div>
                ),
                },
            ]}
            />
        </Form>
      </Drawer>
    </div>
  );
}
