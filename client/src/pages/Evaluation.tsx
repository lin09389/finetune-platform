import {
  BarChartOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import PageHeader from '../components/shared/PageHeader';
import {
  createEvaluationRun,
  getDatasetList,
  getInferenceModels,
  getModelList,
  scoreEvaluationCase,
} from '../services/api';
import { useAppStore } from '../store/appStore';
import type { AppTaskGoal, DatasetInfo, EvaluationRun, ModelInfo } from '../types';

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

type SelectOption = { label: string; value: string };

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

    if (typeof item === 'string') {
      value = item;
      label = item;
    } else if (item && typeof item === 'object') {
      const record = item as Record<string, unknown>;
      value = getStringValue(record, ['id', 'model_id', 'name', 'model_name', 'path']);
      label = getStringValue(record, ['name', 'model_name', 'id', 'model_id', 'path']);
      tag = getStringValue(record, ['backend', 'source', 'type']);
    }

    if (!value || seen.has(value)) continue;
    seen.add(value);
    options.push({
      value,
      label: tag ? `${label || value} · ${tag}` : label || value,
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
  const { models, datasets, setModels, setDatasets, backendStatus } = useAppStore();
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectorLoading, setSelectorLoading] = useState(false);
  const [modelOptions, setModelOptions] = useState<SelectOption[]>(() =>
    normalizeModelOptions(models),
  );
  const [datasetOptions, setDatasetOptions] = useState<SelectOption[]>(() =>
    normalizeDatasetOptions(datasets),
  );
  const watchedScenario = Form.useWatch('scenario', form) as AppTaskGoal | undefined;
  const watchedBaseModel = Form.useWatch('base_model', form) as string | undefined;
  const watchedFinetunedModel = Form.useWatch('finetuned_model', form) as string | undefined;
  const watchedAdapterPath = Form.useWatch('adapter_path', form) as string | undefined;
  const watchedBackend = Form.useWatch('backend', form) as string | undefined;
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
          setModelOptions(normalizeModelOptions(modelItems));
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
      const schema = values.schema ? JSON.parse(values.schema) : undefined;
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
        test_dataset_id: values.test_dataset_id,
        cases: values.prompt
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
      setRun(await createEvaluationRun(payload));
      message.success('评估任务已创建');
    } catch (error: any) {
      message.error(error?.message || '创建评估失败，请检查 JSON schema');
    } finally {
      setLoading(false);
    }
  };

  const handleScore = async (score: 'good' | 'neutral' | 'bad') => {
    if (!run) return;
    const nextRun = await scoreEvaluationCase(run.run_id, { case_index: 0, score });
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
            {datasetLabel}
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

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={9}>
          <Card title="创建评估任务" variant="borderless">
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
              <Form.Item name="scenario" label="应用目标" rules={[{ required: true }]}>
                <Select options={scenarioOptions} />
              </Form.Item>
              <Form.Item name="base_model" label="基础模型" rules={[{ required: true }]}>
                <AutoComplete
                  options={modelOptions}
                  placeholder="选择模型，或输入 qwen2.5:7b"
                  filterOption={(input, option) =>
                    String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                    String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                  notFoundContent={selectorLoading ? '正在加载模型...' : '暂无可选模型，可直接输入'}
                />
              </Form.Item>
              <Form.Item name="finetuned_model" label="微调模型">
                <AutoComplete
                  options={modelOptions}
                  placeholder="选择已合并模型，或输入 outputs/my-run/merged"
                  filterOption={(input, option) =>
                    String(option?.label ?? '').toLowerCase().includes(input.toLowerCase()) ||
                    String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                  notFoundContent={selectorLoading ? '正在加载模型...' : '暂无可选模型，可直接输入'}
                  allowClear
                />
              </Form.Item>
              <Form.Item name="adapter_path" label="Adapter 路径">
                <Input placeholder="outputs/my-run/adapter" />
              </Form.Item>
              <Form.Item name="backend" label="推理后端">
                <Select
                  options={[
                    { label: 'Ollama', value: 'ollama' },
                    { label: 'HuggingFace', value: 'huggingface' },
                    { label: '云端 API', value: 'cloud' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="run_inference" label="自动调用真实推理" valuePropName="checked">
                <Switch checkedChildren="开启" unCheckedChildren="关闭" />
              </Form.Item>
              <Form.Item name="auto_merge_adapter" label="自动合并 Adapter" valuePropName="checked">
                <Switch checkedChildren="开启" unCheckedChildren="关闭" />
              </Form.Item>
              <Form.Item name="test_dataset_id" label="测试数据集 ID">
                <Select
                  options={datasetOptions}
                  placeholder="可选：选择已上传数据集批量评估"
                  loading={selectorLoading}
                  showSearch
                  allowClear
                  optionFilterProp="label"
                  notFoundContent={selectorLoading ? '正在加载数据集...' : '暂无数据集'}
                />
              </Form.Item>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item name="max_tokens" label="最大 Token">
                    <InputNumber min={1} max={4096} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="temperature" label="温度">
                    <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="max_cases" label="最大样本">
                    <InputNumber min={1} max={100} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="prompt" label="测试提示词">
                <Input.TextArea rows={3} placeholder="输入单条测试提示词；也可以选择测试数据集批量评估" />
              </Form.Item>
              <Form.Item name="schema" label="JSON Schema / 字段定义">
                <Input.TextArea rows={3} placeholder='{"company":"string","amount":"number"}' />
              </Form.Item>
              <Form.Item name="base_output" label="基础模型输出">
                <Input.TextArea rows={3} placeholder="可选：填写后会跳过基础模型自动推理" />
              </Form.Item>
              <Form.Item name="finetuned_output" label="微调模型输出">
                <Input.TextArea rows={3} placeholder="可选：填写后会跳过微调模型自动推理" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} icon={<BarChartOutlined />}>
                运行评估
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={15}>
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
                  <Card variant="borderless">创建一次评估后，这里会显示 JSON 合法率、schema 符合率或人工评分指标。</Card>
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
                    <Button onClick={() => handleScore('good')}>好</Button>
                    <Button onClick={() => handleScore('neutral')}>一般</Button>
                    <Button danger onClick={() => handleScore('bad')}>
                      差
                    </Button>
                  </Space>
                }
                variant="borderless"
              >
                {run.warnings?.length ? (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="评估过程中有提示"
                    description={run.warnings.join('；')}
                  />
                ) : null}
                <Table
                  rowKey={(_, index) => String(index)}
                  pagination={false}
                  dataSource={run.cases}
                  columns={[
                    { title: '提示词', dataIndex: 'prompt', ellipsis: true },
                    { title: '基础模型', dataIndex: 'base_output', ellipsis: true },
                    { title: '微调模型', dataIndex: 'finetuned_output', ellipsis: true },
                    { title: '基础模型错误', dataIndex: 'base_output_error', ellipsis: true },
                    { title: '微调模型错误', dataIndex: 'finetuned_output_error', ellipsis: true },
                  ]}
                />
              </Card>
            )}
          </Space>
        </Col>
      </Row>
    </div>
  );
}
