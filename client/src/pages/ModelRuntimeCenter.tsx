import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DeleteOutlined,
  FolderAddOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Input,
  Modal,
  Progress,
  Segmented,
  Space,
  Table,
  Tabs,
  Tag,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import EmptyState from '../components/shared/EmptyState';
import StatusState from '../components/shared/StatusState';
import { useRuntimeContext } from '../runtime/RuntimeContext';
import {
  deleteLocalModel,
  downloadModelFromHuggingFace,
  downloadModelFromModelScope,
  extractApiErrorMessage,
  getDownloadProgress,
  getModelRuntimeOverview,
  importModelFromModelScope,
  searchModels,
  setModelRuntimeSelection,
  type ModelRuntimeModel,
  type ModelRuntimeOverview,
  type ModelRuntimeRecommendation,
} from '../services/api';
import styles from './ModelRuntimeCenter.module.css';

interface DownloadTaskState {
  taskId: string;
  label: string;
  status: string;
  progress: number;
  error?: string;
}

interface ExternalModelSearchResult {
  modelId?: string;
  id?: string;
  name?: string;
  downloads?: number;
  likes?: number;
  source?: string;
  library_name?: string;
  tags?: string[];
}

interface ImportFormState {
  modelName: string;
  modelScopePath: string;
}

const capabilityLabels: Record<string, string> = {
  agent: 'Agent',
  chat: '对话',
  inference: '推理',
  fine_tune: '训练',
  evaluation: '评估',
  embedding: '嵌入',
  knowledge_base: '知识库',
  low_vram: '低显存',
  vision: '视觉',
};

const readinessColor = (state: string) => {
  if (state === 'ready') return 'green';
  if (state === 'blocked') return 'red';
  return 'gold';
};

const backendLabel = (backend: string) => {
  if (backend === 'ollama') return 'Ollama';
  if (backend === 'huggingface') return 'HuggingFace';
  if (backend === 'llama-cpp') return 'llama.cpp';
  return backend;
};

const recommendedSourceLabel = (source: string) =>
  source === 'modelscope' ? 'ModelScope' : 'HuggingFace';

export default function ModelRuntimeCenter() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const runtime = useRuntimeContext();
  const [overview, setOverview] = useState<ModelRuntimeOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('models');
  const [downloadTasks, setDownloadTasks] = useState<Record<string, DownloadTaskState>>({});
  const [searchQuery, setSearchQuery] = useState('');
  const [searchSource, setSearchSource] = useState<'modelscope' | 'huggingface'>('modelscope');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<ModelRuntimeRecommendation[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importForm, setImportForm] = useState<ImportFormState>({
    modelName: 'Qwen2.5-0.5B-Instruct',
    modelScopePath: '',
  });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await getModelRuntimeOverview();
      setOverview(payload);
      setLoadError(null);
      if (payload.active_selection.backend && payload.active_selection.model_id) {
        runtime.actions.setInferenceSelection({
          backend: payload.active_selection.backend,
          modelId: payload.active_selection.model_id,
        });
      }
    } catch (error) {
      const errorMessage = extractApiErrorMessage(error, '加载模型运行中心失败');
      setLoadError(errorMessage);
      message.error(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [message, runtime.actions]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const agentModel = overview?.agent.model || undefined;
  const selectedKey = `${overview?.active_selection.backend || ''}:${overview?.active_selection.model_id || ''}`;

  const bestNextStep = useMemo(() => {
    if (!overview) return '正在检测模型运行环境';
    if (overview.agent.ready) return `Agent 已绑定 ${overview.agent.model_string}`;
    if (overview.summary.local_ready_models > 0) return '已有本地模型；建议再接入 Ollama 作为 Agent 运行模型';
    return '先下载推荐模型，或启动 Ollama 后拉取一个 chat 模型';
  }, [overview]);

  const selectModel = async (model: ModelRuntimeModel, scope: 'global' | 'agent' = 'global') => {
    try {
      await setModelRuntimeSelection({
        backend: model.backend as 'huggingface' | 'ollama' | 'llama-cpp',
        model_id: model.id,
        scope,
      });
      runtime.actions.syncInferenceSelection({
        backend: model.backend,
        modelId: model.id,
      });
      message.success(scope === 'agent' ? '已设为 Agent 默认模型' : '已设为当前运行模型');
      await refresh();
    } catch (error) {
      message.error(extractApiErrorMessage(error, '模型选择失败'));
    }
  };

  const startDownload = async (recommendation: ModelRuntimeRecommendation) => {
    try {
      const result =
        recommendation.source === 'huggingface'
          ? await downloadModelFromHuggingFace(recommendation.repo_id)
          : await downloadModelFromModelScope(recommendation.repo_id);
      const taskId = result.task_id;
      setDownloadTasks((current) => ({
        ...current,
        [taskId]: {
          taskId,
          label: recommendation.name,
          status: 'pending',
          progress: 0,
        },
      }));
      message.success(`已开始下载 ${recommendation.name}`);
      pollDownload(taskId, recommendation.name);
    } catch (error) {
      message.error(extractApiErrorMessage(error, '下载任务启动失败'));
    }
  };

  const pollDownload = (taskId: string, label: string) => {
    const tick = async () => {
      try {
        const progress = await getDownloadProgress(taskId);
        setDownloadTasks((current) => ({
          ...current,
          [taskId]: {
            taskId,
            label,
            status: progress.status,
            progress: progress.progress,
            error: progress.error,
          },
        }));
        if (progress.status === 'completed') {
          message.success(`${label} 下载完成`);
          await refresh();
          return;
        }
        if (progress.status === 'failed' || progress.status === 'cancelled') {
          message.error(progress.error || `${label} 下载失败`);
          return;
        }
        window.setTimeout(tick, 1800);
      } catch (error) {
        setDownloadTasks((current) => ({
          ...current,
          [taskId]: {
            ...(current[taskId] || { taskId, label, progress: 0 }),
            status: 'failed',
            error: extractApiErrorMessage(error, '下载状态读取失败'),
          },
        }));
      }
    };
    window.setTimeout(tick, 1200);
  };

  const runSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const results = await searchModels(searchQuery, 12, searchSource);
      setSearchResults(
        results.map((item: ExternalModelSearchResult) => ({
          repo_id: item.modelId || item.id,
          name: item.name || item.modelId || item.id,
          description: `${item.downloads || 0} 下载 · ${item.likes || 0} 喜欢`,
          size: '外部仓库',
          source: item.source || searchSource,
          category: item.library_name || 'chat',
          fit: 'good',
          why: (item.tags || []).slice(0, 4).join(' / ') || '可下载后进入本地运行中心。',
        })),
      );
    } catch (error) {
      message.error(extractApiErrorMessage(error, '搜索失败'));
    } finally {
      setSearching(false);
    }
  };

  const importModel = async () => {
    if (!importForm.modelName.trim()) {
      message.warning('请输入模型名称');
      return;
    }
    setImporting(true);
    try {
      await importModelFromModelScope(
        importForm.modelName.trim(),
        importForm.modelScopePath.trim() || undefined,
      );
      message.success('模型导入完成');
      setImportOpen(false);
      await refresh();
    } catch (error) {
      message.error(extractApiErrorMessage(error, '导入失败'));
    } finally {
      setImporting(false);
    }
  };

  const deleteModel = (model: ModelRuntimeModel) => {
    Modal.confirm({
      title: `删除 ${model.name}`,
      content: '删除后需要重新下载或导入。Ollama 模型请在 Ollama 中管理。',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteLocalModel(model.id);
          message.success('模型已删除');
          await refresh();
        } catch (error) {
          message.error(extractApiErrorMessage(error, '删除失败'));
        }
      },
    });
  };

  const modelColumns: ColumnsType<ModelRuntimeModel> = [
    {
      title: '模型',
      dataIndex: 'name',
      render: (_, model) => (
        <div className={styles.modelNameCell}>
          <strong>{model.name}</strong>
          <span>{model.path || model.source}</span>
        </div>
      ),
    },
    {
      title: '运行方式',
      dataIndex: 'backend',
      width: 150,
      render: (backend) => <Tag>{backendLabel(backend)}</Tag>,
    },
    {
      title: '能力',
      dataIndex: 'capabilities',
      render: (capabilities: string[]) => (
        <Space size={[4, 4]} wrap>
          {capabilities.map((capability) => (
            <Tag key={capability} color={capability === 'agent' ? 'purple' : 'blue'}>
              {capabilityLabels[capability] || capability}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'readiness',
      width: 180,
      render: (readiness) => (
        <Tag color={readinessColor(readiness.state)} icon={readiness.state === 'ready' ? <CheckCircleOutlined /> : <WarningOutlined />}>
          {readiness.label}
        </Tag>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size_label',
      width: 110,
    },
    {
      title: '操作',
      key: 'actions',
      width: 250,
      render: (_, model) => (
        <Space>
          <Button
            size="small"
            type={selectedKey === `${model.backend}:${model.id}` ? 'primary' : 'default'}
            icon={<ThunderboltOutlined />}
            onClick={() => void selectModel(model)}
          >
            使用
          </Button>
          <Button
            size="small"
            icon={<RobotOutlined />}
            disabled={!model.capabilities.includes('agent') || model.readiness.state !== 'ready'}
            onClick={() => void selectModel(model, 'agent')}
          >
            Agent
          </Button>
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            disabled={model.source === 'ollama'}
            onClick={() => deleteModel(model)}
          />
        </Space>
      ),
    },
  ];

  const recommendationCards = (items: ModelRuntimeRecommendation[]) => (
    <div className={styles.recommendationGrid}>
      {items.map((item) => (
        <article key={`${item.source}:${item.repo_id}`} className={styles.recommendationCard}>
          <div className={styles.cardTopline}>
            <Tag color={item.fit === 'best' ? 'green' : 'blue'}>
              {item.fit === 'best' ? '最适合' : '推荐'}
            </Tag>
            <span>{recommendedSourceLabel(item.source)}</span>
          </div>
          <h3>{item.name}</h3>
          <p>{item.description}</p>
          <div className={styles.cardMeta}>
            <span>{item.size}</span>
            <span>{item.category}</span>
          </div>
          <div className={styles.cardWhy}>{item.why}</div>
          <Button
            type="primary"
            icon={<CloudDownloadOutlined />}
            onClick={() => void startDownload(item)}
          >
            下载
          </Button>
        </article>
      ))}
    </div>
  );

  return (
    <MotionList className={styles.container} stagger={0.06}>
      <MotionItem>
        <section className={styles.commandBand}>
          <div className={styles.commandCopy}>
            <div className={styles.kicker}>
              <ApiOutlined /> 模型运行中心
            </div>
            <h1>{overview?.summary.headline || '正在检测模型运行环境'}</h1>
            <p>{bestNextStep}</p>
            <Space wrap>
              <Button
                type="primary"
                icon={<RobotOutlined />}
                onClick={() => {
                  if (agentModel) {
                    navigate('/agent');
                  } else {
                    setActiveTab('discover');
                  }
                }}
              >
                {agentModel ? '打开 Agent 工作台' : '配置 Agent 模型'}
              </Button>
              <Button icon={<CloudDownloadOutlined />} onClick={() => setActiveTab('discover')}>
                获取模型
              </Button>
              <Button icon={<FolderAddOutlined />} onClick={() => setImportOpen(true)}>
                导入本地模型
              </Button>
              <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void refresh()}>
                刷新
              </Button>
            </Space>
          </div>
          <div className={styles.statusPanel}>
            <div>
              <span>Agent 模型</span>
              <strong>{overview?.agent.model_string || '未配置'}</strong>
            </div>
            <div>
              <span>本地模型</span>
              <strong>{overview?.summary.total_models ?? 0}</strong>
            </div>
            <div>
              <span>Ollama</span>
              <strong>{overview?.summary.ollama_available ? '在线' : '离线'}</strong>
            </div>
            <div>
              <span>模型目录</span>
              <strong title={overview?.environment.models_dir}>{overview?.environment.models_dir || '-'}</strong>
            </div>
          </div>
        </section>
      </MotionItem>

      {loadError ? (
        <MotionItem>
          <StatusState
            tone="error"
            title="模型运行中心暂时无法加载"
            description={`${loadError}。请确认本地后端已启动后重试。`}
            action={{ text: '重试加载', onClick: () => void refresh() }}
          />
        </MotionItem>
      ) : null}

      {overview && !overview.agent.ready ? (
        <MotionItem>
          <Alert
            type={overview.summary.local_ready_models > 0 ? 'warning' : 'info'}
            showIcon
            message="Agent 优先体验需要一个可工具调用的模型"
            description={overview.agent.message}
            action={
              <Space>
                <Button size="small" onClick={() => setActiveTab('discover')}>
                  查看推荐
                </Button>
                <Button size="small" onClick={() => navigate('/cloud-api')}>
                  云端 API
                </Button>
              </Space>
            }
          />
        </MotionItem>
      ) : null}

      {Object.values(downloadTasks).length > 0 ? (
        <MotionItem>
          <section className={styles.downloadBand}>
            {Object.values(downloadTasks).map((task) => (
              <div key={task.taskId} className={styles.downloadItem}>
                <div>
                  <strong>{task.label}</strong>
                  <Tag color={task.status === 'failed' ? 'red' : task.status === 'completed' ? 'green' : 'blue'}>
                    {task.status}
                  </Tag>
                </div>
                <Progress percent={Math.round(task.progress || 0)} status={task.status === 'failed' ? 'exception' : undefined} />
                {task.error ? <span className={styles.errorText}>{task.error}</span> : null}
              </div>
            ))}
          </section>
        </MotionItem>
      ) : null}

      <MotionItem>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'models',
              label: '本地与运行时',
              children: (
                <section className={styles.sectionSurface}>
                  {overview?.local_models.length ? (
                    <Table
                      rowKey={(model) => `${model.backend}:${model.id}`}
                      columns={modelColumns}
                      dataSource={overview.local_models}
                      pagination={{ pageSize: 8 }}
                      loading={loading}
                    />
                  ) : (
                    <EmptyState
                      compact
                      title="还没有可用模型"
                      description="下载或导入模型后，即可在本机推理或配置 Agent。"
                      action={{ text: '下载推荐模型', onClick: () => setActiveTab('discover') }}
                    />
                  )}
                </section>
              ),
            },
            {
              key: 'discover',
              label: '获取模型',
              children: (
                <section className={styles.sectionSurface}>
                  {overview?.recommended_models.length ? recommendationCards(overview.recommended_models) : (
                    <EmptyState
                      compact
                      title="暂无推荐模型"
                      description="可以搜索 ModelScope 或 HuggingFace 的模型。"
                    />
                  )}
                  <div className={styles.searchStrip}>
                    <Segmented
                      value={searchSource}
                      onChange={(value) => setSearchSource(value as 'modelscope' | 'huggingface')}
                      options={[
                        { label: 'ModelScope', value: 'modelscope' },
                        { label: 'HuggingFace', value: 'huggingface' },
                      ]}
                    />
                    <Input.Search
                      value={searchQuery}
                      onChange={(event) => setSearchQuery(event.target.value)}
                      onSearch={() => void runSearch()}
                      loading={searching}
                      placeholder="搜索 Qwen、Llama、embedding..."
                      enterButton={<SearchOutlined />}
                    />
                  </div>
                  {searchResults.length ? recommendationCards(searchResults) : null}
                </section>
              ),
            },
            {
              key: 'diagnostics',
              label: '诊断',
              children: (
                <section className={styles.sectionSurface}>
                  <div className={styles.diagnosticsGrid}>
                    <div>
                      <h3>环境</h3>
                      <dl>
                        <dt>下载源</dt>
                        <dd>{overview?.environment.model_source || '-'}</dd>
                        <dt>Ollama 地址</dt>
                        <dd>{overview?.environment.ollama_base_url || '-'}</dd>
                        <dt>硬件档位</dt>
                        <dd>
                          {typeof overview?.environment.hardware_profile?.profile === 'string'
                            ? overview.environment.hardware_profile.profile
                            : 'unknown'}
                        </dd>
                      </dl>
                    </div>
                    <div>
                      <h3>诊断事件</h3>
                      {overview?.diagnostics.length ? (
                        overview.diagnostics.map((item, index) => (
                          <Alert
                            key={`${item.kind}:${index}`}
                            type={item.severity === 'error' ? 'error' : 'warning'}
                            showIcon
                            message={item.kind}
                            description={item.message}
                            className={styles.diagnosticAlert}
                          />
                        ))
                      ) : (
                        <Alert type="success" showIcon message="未发现模型接入异常" />
                      )}
                    </div>
                  </div>
                </section>
              ),
            },
          ]}
        />
      </MotionItem>

      <Modal
        title="导入 ModelScope 本地目录"
        open={importOpen}
        okText="导入"
        cancelText="取消"
        confirmLoading={importing}
        onCancel={() => setImportOpen(false)}
        onOk={() => void importModel()}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Input
            value={importForm.modelName}
            onChange={(event) => setImportForm((current) => ({ ...current, modelName: event.target.value }))}
            placeholder="模型名称，如 Qwen2.5-0.5B-Instruct"
          />
          <Input
            value={importForm.modelScopePath}
            onChange={(event) => setImportForm((current) => ({ ...current, modelScopePath: event.target.value }))}
            placeholder="可选：ModelScope 缓存目录路径"
          />
        </Space>
      </Modal>
    </MotionList>
  );
}
