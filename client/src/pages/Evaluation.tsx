import {
  BarChartOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  FileSearchOutlined,
  LikeOutlined,
  DislikeOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tabs,
  Tag,
  message,
  Progress,
  Typography,
} from 'antd';
import { useEffect, useMemo, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import PageHeader from '../components/shared/PageHeader';
import {
  createEvaluationRun,
  getDatasetList,
  getInferenceModels,
  getModelList,
  scoreEvaluationCase,
  getEvaluationRun,
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
  const seen = new Set<string>();
  const options: SelectOption[] = [];

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

    if (!value || seen.has(value)) continue;
    seen.add(value);
    options.push({
      value,
      label: tag ? `${label || value} · ${tag}` : label || value,
      backend: backend || undefined,
    });
  }

  return options.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
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
  const [searchParams] = useSearchParams();
  const { models, datasets, trainingRecords, setModels, setDatasets, backendStatus } = useAppStore();
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [pollingRunId, setPollingRunId] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);
  const [selectorLoading, setSelectorLoading] = useState(false);
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
  const watchedDatasetId = Form.useWatch('test_dataset_id', form) as string | undefined;
  const watchedTrainingTaskId = Form.useWatch('training_task_id', form) as string | undefined;
  const watchedRunInference = Form.useWatch('run_inference', form) as boolean | undefined;
  const watchedAutoMergeAdapter = Form.useWatch('auto_merge_adapter', form) as boolean | undefined;

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

    stringKeys.forEach((key) => {
      const value = searchParams.get(key);
      if (value) values[key] = value;
    });

    numberKeys.forEach((key) => {
      const value = searchParams.get(key);
      if (!value) return;
      const numeric = Number(value);
      if (Number.isFinite(numeric)) values[key] = numeric;
    });

    const runInference = searchParams.get('run_inference');
    if (runInference !== null) {
      values.run_inference = runInference !== 'false';
    }
    const autoMergeAdapter = searchParams.get('auto_merge_adapter');
    if (autoMergeAdapter !== null) {
      values.auto_merge_adapter = autoMergeAdapter !== 'false';
    }

    if (Object.keys(values).length) {
      form.setFieldsValue(values);
    }
  }, [form, searchParams]);

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

  const pollEvaluationStatus = async (runId: string) => {
    try {
      const data = await getEvaluationRun(runId);
      setRun(data);
      if (data.status === 'pending' || data.status === 'running') {
        pollingRef.current = window.setTimeout(() => pollEvaluationStatus(runId), 2000);
      } else {
        setPollingRunId(null);
        setLoading(false);
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

  const handleCreateRun = async (values: {
    scenario: AppTaskGoal;
    base_model: string;
    finetuned_model?: string;
    adapter_path?: string;
    backend?: string;
    run_inference?: boolean;
    auto_merge_adapter?: boolean;
    max_tokens?: number;
    temperature?: number;
    max_cases?: number;
    test_dataset_id?: string;
    prompt?: string;
    expected_output?: string;
    schema?: string;
    base_output?: string;
    finetuned_output?: string;
  }) => {
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
      message.warning('缺少 Adapter 路径，请先从训练历史进入评估，或手动填写 Adapter 路径');
      return;
    }

    const params = new URLSearchParams();
    params.set('training_task_id', trainingTaskId || 'manual-evaluation');
    params.set('base_model', baseModel);
    params.set('adapter_path', adapterPath);
    if (mergedModelPath) params.set('merged_model_path', mergedModelPath);
    params.set(
      'model_alias',
      watchedScenario === 'qa_assistant' ? 'qa-assistant-finetuned' : 'structured-extraction-finetuned',
    );

    navigate(`/deployment?${params.toString()}`);
  };

  const metricEntries = Object.entries(run?.metrics ?? {});
  const scenarioLabel =
    scenarioOptions.find((option) => option.value === (watchedScenario || 'structured_extraction'))
      ?.label || '结构化输出/信息抽取';
  const datasetLabel =
    datasetOptions.find((option) => option.value === watchedDatasetId)?.label ||
    watchedDatasetId ||
    '单条提示词';
  const backendLabel =
    watchedBackend === 'huggingface'
      ? 'HuggingFace'
      : watchedBackend === 'cloud'
        ? '云端 API'
        : 'Ollama';

  return (
    <div style={{ padding: 24 }}>
      <PageHeader
        title="评估实验室"
        icon={<FileSearchOutlined />}
        helpTooltip="对比基础模型和微调模型在问答、结构化抽取场景下的输出效果。"
      />

      <Card title="当前评估对象" variant="borderless" style={{ marginBottom: 16 }}>
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, lg: 3 }}
          styles={{
            label: { color: '#6b7280', width: 96 },
            content: { wordBreak: 'break-all' },
          }}
        >
          <Descriptions.Item label="应用目标">
            <Tag color={watchedScenario === 'qa_assistant' ? 'green' : 'blue'}>
              {scenarioLabel}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="基础模型">
            {watchedBaseModel || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="测试数据">
            {testMode === 'dataset' ? datasetLabel : '单条提示词'}
          </Descriptions.Item>
          <Descriptions.Item label="训练任务">
            {watchedTrainingTaskId || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="微调模型">
            {watchedFinetunedModel ||
              (watchedAdapterPath && watchedAutoMergeAdapter ? '由 Adapter 自动合并生成' : '-')}
          </Descriptions.Item>
          <Descriptions.Item label="Adapter">
            {watchedAdapterPath || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="推理方式">
            <Space size={8} wrap>
              <Tag color="geekblue">{backendLabel}</Tag>
              <Tag color={watchedRunInference === false ? 'default' : 'success'}>
                {watchedRunInference === false ? '手动输出' : '真实推理'}
              </Tag>
              {watchedAdapterPath ? (
                <Tag color={watchedAutoMergeAdapter === false ? 'default' : 'cyan'}>
                  {watchedAutoMergeAdapter === false ? '不自动合并' : '自动合并 Adapter'}
                </Tag>
              ) : null}
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Row gutter={[24, 24]}>
        <Col xs={24} lg={8}>
          <Card title="配置与运行" variant="borderless">
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
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 500, marginBottom: 16, fontSize: 15 }}>1. 模型配置</div>
                <Form.Item name="scenario" label="应用目标" rules={[{ required: true }]}>
                  <Select options={scenarioOptions} />
                </Form.Item>
                <Form.Item name="base_model" label="基础模型" rules={[{ required: true }]}>
                  <AutoComplete
                    options={modelOptions}
                    placeholder={watchedBackend === 'huggingface' ? '选择本地模型目录或名称' : '选择模型，或输入 qwen2.5:7b'}
                    filterOption={(input, option) =>
                      String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                      String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                    notFoundContent={selectorLoading ? '正在加载模型...' : '当前后端下暂无可选模型，可手动输入'}
                  />
                </Form.Item>
                <Form.Item name="finetuned_model" label="微调模型">
                  <AutoComplete
                    options={modelOptions}
                    placeholder={watchedBackend === 'huggingface' ? '选择已合并模型目录，或输入本地路径' : '选择 Ollama 模型 tag'}
                    filterOption={(input, option) =>
                      String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                      String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                    notFoundContent={selectorLoading ? '正在加载模型...' : '当前后端下暂无可选模型，可手动输入'}
                    allowClear
                  />
                </Form.Item>
                {watchedBackend === 'ollama' && (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="Ollama 后端只能使用 Ollama 已安装模型"
                    description="例如 `qwen2.5:7b`。如果你要评估本地目录里的 HuggingFace 模型，请把后端切换为 HuggingFace。"
                  />
                )}
                <Form.Item name="adapter_path" label="Adapter 路径" rules={[
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
                    placeholder="选择历史训练的 Adapter，或输入 outputs/my-run/adapter"
                    filterOption={(input, option) =>
                      String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                      String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                  />
                </Form.Item>
              </div>

              <Divider style={{ margin: '16px 0' }} />

              <div style={{ marginBottom: 8 }}>
                <div style={{ fontWeight: 500, marginBottom: 16, fontSize: 15 }}>2. 测试内容</div>
                <Tabs
                  activeKey={testMode}
                  onChange={(k) => setTestMode(k as 'dataset' | 'single')}
                  items={[
                    {
                      key: 'dataset',
                      label: '数据集评估',
                      children: (
                        <div style={{ paddingTop: 8 }}>
                          <Form.Item name="test_dataset_id" label="测试数据集">
                            <Select
                              options={datasetOptions}
                              placeholder="选择已上传数据集批量评估"
                              loading={selectorLoading}
                              showSearch
                              allowClear
                              optionFilterProp="label"
                              notFoundContent={selectorLoading ? '正在加载数据集...' : '暂无数据集'}
                            />
                          </Form.Item>
                          <Form.Item name="max_cases" label="最大抽取样本数">
                            <InputNumber min={1} max={100} style={{ width: '100%' }} />
                          </Form.Item>
                        </div>
                      ),
                    },
                    {
                      key: 'single',
                      label: '单条手动评估',
                      children: (
                        <div style={{ paddingTop: 8 }}>
                          <Form.Item name="prompt" label="测试提示词">
                            <Input.TextArea rows={3} placeholder="输入单条测试提示词" />
                          </Form.Item>
                          <Collapse
                            ghost
                            style={{ padding: 0, marginLeft: -16 }}
                            items={[
                              {
                                key: 'manual-output',
                                label: <span style={{ fontSize: 13, color: '#6b7280' }}>高级：手动填入模型输出</span>,
                                children: (
                                  <>
                                    <Form.Item name="base_output" label="基础模型输出" style={{ marginBottom: 12 }}>
                                      <Input.TextArea rows={3} placeholder="可选：填写后跳过基础模型推理" />
                                    </Form.Item>
                                    <Form.Item name="finetuned_output" label="微调模型输出" style={{ marginBottom: 0 }}>
                                      <Input.TextArea rows={3} placeholder="可选：填写后跳过微调模型推理" />
                                    </Form.Item>
                                  </>
                                ),
                              },
                            ]}
                          />
                        </div>
                      ),
                    },
                  ]}
                />
                <Form.Item name="schema" label="JSON Schema / 字段定义" style={{ marginTop: 16 }}>
                  <div style={{ height: 160, border: '1px solid #d9d9d9', borderRadius: 6, overflow: 'hidden' }}>
                    <Form.Item name="schema" noStyle>
                      <JSONDataEditor 
                        readOnly={false}
                        height="100%"
                      />
                    </Form.Item>
                  </div>
                </Form.Item>
              </div>

              <Divider style={{ margin: '16px 0' }} />

              <Collapse
                ghost
                style={{ padding: 0, marginLeft: -16, marginBottom: 24 }}
                items={[
                  {
                    key: 'advanced',
                    label: <span style={{ fontWeight: 500, fontSize: 15, color: '#1f2937' }}>3. 推理参数与高级设置</span>,
                    children: (
                      <div style={{ paddingTop: 8, paddingLeft: 16 }}>
                        <Row gutter={12}>
                          <Col span={12}>
                            <Form.Item name="backend" label="推理后端">
                              <Select
                                options={[
                                  { label: 'Ollama', value: 'ollama' },
                                  { label: 'HuggingFace', value: 'huggingface' },
                                  { label: '云端 API', value: 'cloud' },
                                ]}
                              />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item name="temperature" label="温度">
                              <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item name="max_tokens" label="最大 Token">
                              <InputNumber min={1} max={4096} style={{ width: '100%' }} />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item name="run_inference" label="自动调用推理" valuePropName="checked">
                              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                            </Form.Item>
                          </Col>
                          <Col span={24}>
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

              <Button type="primary" htmlType="submit" disabled={pollingRunId !== null} loading={loading} icon={<BarChartOutlined />} block size="large">
                {pollingRunId ? '正在评估...' : '开始评估'}
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={16}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Row gutter={[16, 16]}>
              {metricEntries.map(([key, value]) => (
                <Col xs={12} md={8} key={key}>
                  <Card variant="borderless">
                    <Statistic
                      title={metricLabels[key] || key}
                      value={value}
                      precision={typeof value === 'number' && value < 1 ? 2 : 0}
                    />
                  </Card>
                </Col>
              ))}
              {!metricEntries.length && (
                <Col span={24}>
                  <Card variant="borderless">
                    <div style={{ color: '#6b7280', padding: '24px 0', textAlign: 'center' }}>
                      完成一次评估后，这里会显示 JSON 合法率、Schema 符合率或人工评分等指标。
                    </div>
                  </Card>
                </Col>
              )}
            </Row>

            {run && (
              <Card
                title={
                  <Space>
                    <CheckCircleOutlined />
                    <span>{run.run_id}</span>
                    <Tag color="blue">{getScenarioLabel(run.scenario)}</Tag>
                  </Space>
                }
                extra={
                  <Space>
                    <Button icon={<CloudUploadOutlined />} onClick={openDeployment}>
                      进入部署
                    </Button>
                  </Space>
                }
                variant="borderless"
              >
                {(run.status === 'pending' || run.status === 'running') && (
                  <div style={{ textAlign: 'center', padding: '40px 0' }}>
                    <Progress
                      type="circle"
                      percent={run.cases ? Math.round((run.base_outputs?.filter(Boolean).length + run.finetuned_outputs?.filter(Boolean).length) / (run.cases.length * 2) * 100) : 0}
                      status="active"
                    />
                    <div style={{ marginTop: 16, color: '#6b7280' }}>
                      模型正在进行推理，可能需要几分钟时间，请耐心等待...
                    </div>
                  </div>
                )}
                
                {run.warnings?.length ? (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="评估过程中有提示"
                    description={run.warnings.join('；')}
                  />
                ) : null}

                {(run.status === 'completed' || run.status === 'completed_with_warnings') && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    {run.cases?.map((record: any, index: number) => (
                      <Card 
                        key={index}
                        size="small"
                        title={<Text type="secondary">样本 #{index + 1}</Text>}
                        extra={
                          <Space size={4}>
                            <Button 
                              size="small" 
                              type={record.human_score?.score === 'good' ? 'primary' : 'default'}
                              icon={<LikeOutlined />} 
                              onClick={() => handleScore(index, 'good')}
                            >
                              好
                            </Button>
                            <Button 
                              size="small"
                              type={record.human_score?.score === 'neutral' ? 'primary' : 'default'}
                              icon={<MinusCircleOutlined />} 
                              onClick={() => handleScore(index, 'neutral')}
                            >
                              一般
                            </Button>
                            <Button 
                              size="small" 
                              danger={record.human_score?.score === 'bad'}
                              type={record.human_score?.score === 'bad' ? 'primary' : 'default'}
                              icon={<DislikeOutlined />} 
                              onClick={() => handleScore(index, 'bad')}
                            >
                              差
                            </Button>
                          </Space>
                        }
                        styles={{ body: { padding: '12px 16px' } }}
                      >
                        <div style={{ marginBottom: 16 }}>
                          <div style={{ fontWeight: 500, marginBottom: 8, color: '#374151' }}>提示词</div>
                          <div style={{ padding: '8px 12px', background: '#f3f4f6', borderRadius: 6, whiteSpace: 'pre-wrap', fontFamily: 'inherit', color: '#4b5563' }}>
                            {String(record.prompt || '')}
                          </div>
                        </div>
                        
                        <Row gutter={16}>
                          <Col span={12}>
                            <div style={{ fontWeight: 500, marginBottom: 8, color: '#374151' }}>
                              基础模型 <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>{run.base_model}</Text>
                            </div>
                            <div style={{ padding: '8px 12px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, minHeight: 80, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
                              {record.base_output_error ? (
                                <Text type="danger">{String(record.base_output_error)}</Text>
                              ) : (
                                String(record.base_output || '')
                              )}
                            </div>
                          </Col>
                          <Col span={12}>
                            <div style={{ fontWeight: 500, marginBottom: 8, color: '#374151' }}>
                              微调模型 <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>{run.finetuned_model || run.adapter_path}</Text>
                            </div>
                            <div style={{ padding: '8px 12px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, minHeight: 80, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
                              {record.finetuned_output_error ? (
                                <Text type="danger">{String(record.finetuned_output_error)}</Text>
                              ) : (
                                String(record.finetuned_output || '')
                              )}
                            </div>
                          </Col>
                        </Row>
                      </Card>
                    ))}
                  </div>
                )}
              </Card>
            )}
          </Space>
        </Col>
      </Row>
    </div>
  );
}
