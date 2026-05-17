// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockUseAppStore = vi.hoisted(() => vi.fn());
const mockUseRuntimeContext = vi.hoisted(() => vi.fn());
const mockGetTrainingStatus = vi.hoisted(() => vi.fn());
const mockCheckTrainingResources = vi.hoisted(() => vi.fn());
const mockGetTrainingFailureAnalytics = vi.hoisted(() => vi.fn());
const mockGetTrainingHistory = vi.hoisted(() => vi.fn());
const mockGetTrainingCheckpoints = vi.hoisted(() => vi.fn());
const mockGetTrainingRecoveryOptions = vi.hoisted(() => vi.fn());
const mockGetTrainingOverviewV2 = vi.hoisted(() => vi.fn());
const mockResumeTraining = vi.hoisted(() => vi.fn());
const mockSubscribeTrainingProgress = vi.hoisted(() => vi.fn(() => vi.fn()));
const mockSubscribeTrainingEventsV2 = vi.hoisted(() => vi.fn(() => vi.fn()));
const mockGetDatasetList = vi.hoisted(() => vi.fn());
const mockAnalyzeDataset = vi.hoisted(() => vi.fn());
const mockPreviewDataset = vi.hoisted(() => vi.fn());
const mockTransformDataset = vi.hoisted(() => vi.fn());
const mockSplitDataset = vi.hoisted(() => vi.fn());
const mockDeleteDataset = vi.hoisted(() => vi.fn());
const mockUploadDataset = vi.hoisted(() => vi.fn());
const mockGetBackends = vi.hoisted(() => vi.fn());
const mockGetModelList = vi.hoisted(() => vi.fn());
const mockGetInferenceModels = vi.hoisted(() => vi.fn());
const mockGetOllamaStatus = vi.hoisted(() => vi.fn());
const mockListInferenceEngines = vi.hoisted(() => vi.fn());
const mockGetPerformanceStats = vi.hoisted(() => vi.fn());
const mockGetPerformanceRecommendations = vi.hoisted(() => vi.fn());
const mockGetSavedCloudProviders = vi.hoisted(() => vi.fn());
const mockGetSavedCloudProviderData = vi.hoisted(() => vi.fn());
const mockGetPrimaryAgents = vi.hoisted(() => vi.fn());
const mockCreateEvaluationRun = vi.hoisted(() => vi.fn());
const mockScoreEvaluationCase = vi.hoisted(() => vi.fn());
const mockCreateDeploymentPackage = vi.hoisted(() => vi.fn());
const mockListDeploymentPackages = vi.hoisted(() => vi.fn());
const mockGetDeploymentPackage = vi.hoisted(() => vi.fn());
const mockDeleteDeploymentPackage = vi.hoisted(() => vi.fn());
const mockFetch = vi.hoisted(() => vi.fn());
const mockLoadSessions = vi.hoisted(() => vi.fn());
const mockCreateSession = vi.hoisted(() => vi.fn());
const mockDeleteSession = vi.hoisted(() => vi.fn());
const mockDeleteMessage = vi.hoisted(() => vi.fn());
const mockClearMessages = vi.hoisted(() => vi.fn());
const mockUpdateSettings = vi.hoisted(() => vi.fn());
const mockSendMessage = vi.hoisted(() => vi.fn());
const mockSendCloudMessage = vi.hoisted(() => vi.fn());
const mockStopStream = vi.hoisted(() => vi.fn());
const mockSyncInferenceSelection = vi.hoisted(() => vi.fn());
const mockSetInferenceSelection = vi.hoisted(() => vi.fn());
const mockSetTrainingSelection = vi.hoisted(() => vi.fn());
const mockSyncKnowledgeCollection = vi.hoisted(() => vi.fn());
const mockRefreshInference = vi.hoisted(() => vi.fn());
const mockRefreshKnowledge = vi.hoisted(() => vi.fn());
const mockRefreshBootstrap = vi.hoisted(() => vi.fn());
const mockGetDeviceInfo = vi.hoisted(() => vi.fn());
const mockNotify = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  emit: vi.fn(),
}));

vi.stubGlobal('fetch', mockFetch);

vi.mock('../store/appStore', () => ({
  useAppStore: mockUseAppStore,
}));

vi.mock('../runtime/RuntimeContext', () => ({
  useRuntimeContext: mockUseRuntimeContext,
}));

vi.mock('../utils/notify', () => ({
  notify: mockNotify,
}));

vi.mock('../services/trainingApi', () => ({
  checkTrainingResources: mockCheckTrainingResources,
  getTrainingFailureAnalytics: mockGetTrainingFailureAnalytics,
  getTrainingStatus: mockGetTrainingStatus,
  getTrainingHistory: mockGetTrainingHistory,
  getTrainingCheckpoints: mockGetTrainingCheckpoints,
  getTrainingRecoveryOptions: mockGetTrainingRecoveryOptions,
  getTrainingOverviewV2: mockGetTrainingOverviewV2,
  resumeTraining: mockResumeTraining,
  startTraining: vi.fn(),
  stopTraining: vi.fn(),
  subscribeTrainingProgress: mockSubscribeTrainingProgress,
  subscribeTrainingEventsV2: mockSubscribeTrainingEventsV2,
  startSwiftTraining: vi.fn(),
}));

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
  analyzeDataset: mockAnalyzeDataset,
  createDeploymentPackage: mockCreateDeploymentPackage,
  createEvaluationRun: mockCreateEvaluationRun,
  deleteDataset: mockDeleteDataset,
  deleteDeploymentPackage: mockDeleteDeploymentPackage,
  getDatasetList: mockGetDatasetList,
  getBackends: mockGetBackends,
  getDeploymentPackage: mockGetDeploymentPackage,
  getDeviceInfo: mockGetDeviceInfo,
  getInferenceModels: mockGetInferenceModels,
  getModelList: mockGetModelList,
  getOllamaStatus: mockGetOllamaStatus,
  listDeploymentPackages: mockListDeploymentPackages,
  listInferenceEngines: mockListInferenceEngines,
  previewDataset: mockPreviewDataset,
  scoreEvaluationCase: mockScoreEvaluationCase,
  splitDataset: mockSplitDataset,
  transformDataset: mockTransformDataset,
  uploadDataset: mockUploadDataset,
  getPerformanceStats: mockGetPerformanceStats,
  getPerformanceRecommendations: mockGetPerformanceRecommendations,
  getSavedCloudProviders: mockGetSavedCloudProviders,
  getSavedCloudProviderData: mockGetSavedCloudProviderData,
  getPrimaryAgents: mockGetPrimaryAgents,
  streamInference: vi.fn(),
  streamGenerate: vi.fn(),
  switchBackend: vi.fn(),
}));

vi.mock('../store/chatStore', () => ({
  useChatStore: () => ({
    sessions: [],
    messages: [],
    settings: {
      backend: 'huggingface',
      modelId: '',
      useKnowledge: false,
      useMemory: false,
    },
    isLoading: false,
    cloudConfig: {
      useCloudAI: false,
      config: null,
      providers: [],
      selectedModel: '',
    },
    setCloudConfig: vi.fn(),
    createSession: mockCreateSession,
    loadSession: vi.fn(),
    deleteSession: mockDeleteSession,
    loadSessions: mockLoadSessions,
    deleteMessage: mockDeleteMessage,
    clearMessages: mockClearMessages,
    updateSettings: mockUpdateSettings,
  }),
}));

vi.mock('../hooks/chat/useChatStream', () => ({
  useChatStream: () => ({
    sendMessage: mockSendMessage,
    sendCloudMessage: mockSendCloudMessage,
    stop: mockStopStream,
    isStreaming: false,
  }),
}));

vi.mock('../theme', () => ({
  useTheme: () => ({
    theme: 'light',
    toggleTheme: vi.fn(),
  }),
}));

vi.mock('../hooks/useResponsive', () => ({
  useResponsive: () => ({
    isMobile: false,
  }),
}));

vi.mock('../components/chat/ChatHeader', () => ({
  default: () => <div>Mock Chat Header</div>,
}));

vi.mock('../components/ChatMessage', () => ({
  default: () => <div>Mock Chat Message</div>,
}));

vi.mock('../components/chat/ChatInput', () => ({
  default: () => <div>Mock Chat Input</div>,
}));

vi.mock('../components/ChatHistoryDrawer', () => ({
  default: () => <div>Mock Chat History Drawer</div>,
}));

vi.mock('../components/MemoryManager', () => ({
  default: () => <div>Mock Memory Manager</div>,
}));

vi.mock('../pages/APIKeyManager', () => ({
  default: () => <div>Mock API Key Manager</div>,
}));

vi.mock('../components/shared/GlassCard', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../components/shared/AnimatedLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../pages/Training/components/ConfigForm', () => ({
  default: ({
    form,
  }: {
    form: {
      setFieldsValue: (values: Record<string, unknown>) => void;
      getFieldValue: (name: string) => unknown;
    };
  }) => (
    <div>
      <button type="button" onClick={() => form.setFieldsValue({ modelId: 'train-model-1' })}>
        Mock Select Training Model
      </button>
      <div>Mock Config Form</div>
      <div data-testid="mock-training-model">{String(form.getFieldValue('modelId') || '')}</div>
    </div>
  ),
}));

vi.mock('../pages/Training/components/ProgressPanel', () => ({
  default: () => <div>Mock Progress Panel</div>,
}));

vi.mock('../pages/Training/components/LossChart', () => ({
  default: () => <div>Mock Loss Chart</div>,
}));

vi.mock('../components/SwiftChecker', () => {
  function MockSwiftChecker({ onStatusChange }: { onStatusChange: (status: { available: boolean }) => void }) {
    React.useEffect(() => {
      onStatusChange({ available: false });
    }, [onStatusChange]);
    return <div>Mock Swift Checker</div>;
  }
  return { default: MockSwiftChecker };
});

vi.mock('../components/TrainingChart', () => ({
  default: () => <div>Mock Training Chart</div>,
}));

vi.mock('react-virtuoso', () => {
  function MockVirtuoso({
    data,
    itemContent,
    totalCount,
  }: {
    data?: unknown[];
    itemContent?: (index: number, item: unknown) => React.ReactNode;
    totalCount?: number;
  }) {
    const items = data || Array.from({ length: totalCount || 0 }, (_, index) => index);
    return <div>{items.map((item, index) => <div key={index}>{itemContent?.(index, item)}</div>)}</div>;
  }
  return { Virtuoso: MockVirtuoso };
});

import ChatPage from '../pages/ChatNew';
import Dashboard from '../pages/Dashboard';
import DatasetManager from '../pages/DatasetManager';
import Deployment from '../pages/Deployment';
import Evaluation from '../pages/Evaluation';
import Inference from '../pages/Inference';
import KnowledgeBase from '../pages/KnowledgeBase';
import TrainingPage from '../pages/Training';

const renderWithRouter = (ui: React.ReactElement, initialEntries = ['/']) =>
  render(<MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>);

describe('GA smoke pages', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAppStore.mockReturnValue({
      models: [{ id: 'base-model', name: '基础模型' }],
      datasets: [{ id: 'dataset-1', name: '客服问答集', samples: 12, size: 1024, format: 'jsonl', path: 'datasets/dataset-1' }],
      backendStatus: 'connected',
      isTraining: false,
      setIsTraining: vi.fn(),
      addTrainingRecord: vi.fn(),
      setModels: vi.fn(),
      setDatasets: vi.fn(),
      setTrainingRecords: vi.fn(),
      removeDataset: vi.fn(),
      addDataset: vi.fn(),
      trainingRecords: [
        {
          id: 'train-1',
          status: 'completed',
          modelName: '基础模型',
          datasetName: '客服问答集',
          method: 'qlora',
          startTime: new Date().toISOString(),
          outputPath: 'outputs/train-1',
          checkpointPath: 'outputs/train-1/adapter',
          adapterPath: 'outputs/train-1/adapter',
          baseModelId: 'base-model',
          datasetId: 'dataset-1',
          taskGoal: 'qa_assistant',
          config: { modelId: 'base-model', datasetId: 'dataset-1', method: 'qlora' },
        },
      ],
      deviceInfo: {
        vram_free: 6,
        vram_total: 8,
        memory_free: 12,
        memory_total: 16,
      },
      setDeviceInfo: vi.fn(),
    });

    mockUseRuntimeContext.mockReturnValue({
      observed: {
        backendStatus: 'connected',
        inference: {
          backends: [
            { id: 'ollama', name: 'Ollama', available: false },
            { id: 'huggingface', name: 'HuggingFace', available: true },
          ],
          currentBackend: 'ollama',
          huggingfaceModels: [],
          ollamaModels: [],
          ollamaAvailable: false,
        },
        knowledge: {
          collections: [],
          embedderStatus: { loaded: false, error: 'unavailable' },
        },
      },
      selected: {
        training: {},
        inference: {
          backend: 'ollama',
          modelId: undefined,
        },
        knowledge: {},
      },
      derived: {
        activeBackend: 'ollama',
        activeModelId: 'runtime-active-model',
        activeKnowledgeCollection: 'default',
        availableModelCount: 0,
        runtimeStatus: 'degraded',
        warnings: [],
      },
      actions: {
        refreshBootstrap: mockRefreshBootstrap,
        refreshInference: mockRefreshInference,
        refreshKnowledge: mockRefreshKnowledge,
        setTrainingSelection: mockSetTrainingSelection,
        setInferenceSelection: mockSetInferenceSelection,
        setKnowledgeSelection: vi.fn(),
        syncInferenceSelection: mockSyncInferenceSelection,
        syncKnowledgeCollection: mockSyncKnowledgeCollection,
      },
      backendStatus: 'connected',
      inference: {
        backends: [
          { id: 'ollama', name: 'Ollama', available: false },
          { id: 'huggingface', name: 'HuggingFace', available: true },
        ],
        currentBackend: 'ollama',
        selectedBackend: 'ollama',
        selectedModelId: undefined,
        huggingfaceModels: [],
        ollamaModels: [],
        availableModelCount: 0,
        ollamaAvailable: false,
        refresh: vi.fn(),
      },
      knowledge: {
        collections: [],
        selectedCollectionId: 'default',
        embedderStatus: { loaded: false, error: 'unavailable' },
        refresh: vi.fn(),
      },
      chat: {
        backend: 'huggingface',
        modelId: '',
        useKnowledge: false,
        knowledgeCollection: undefined,
        useMemory: false,
        update: vi.fn(),
      },
      training: {},
      summary: {
        activeBackend: 'ollama',
        activeModelId: 'runtime-active-model',
        activeKnowledgeCollection: 'default',
        runtimeStatus: 'ready',
        storageStatus: 'ready',
        warnings: [],
      },
      setTrainingSelection: mockSetTrainingSelection,
      setInferenceSelection: mockSetInferenceSelection,
      setKnowledgeSelection: vi.fn(),
      syncInferenceSelection: mockSyncInferenceSelection,
      syncKnowledgeCollection: mockSyncKnowledgeCollection,
    });
    mockGetDeviceInfo.mockResolvedValue({
      vram_free: 6,
      vram_total: 8,
      memory_free: 12,
      memory_total: 16,
    });
    mockGetDatasetList.mockResolvedValue([
      { id: 'dataset-1', name: '客服问答集', samples: 12, size: 1024, format: 'jsonl', path: 'datasets/dataset-1' },
    ]);
    mockAnalyzeDataset.mockResolvedValue({
      detected_format: 'faq_qa',
      field_candidates: { input: ['question'], output: ['answer'] },
      sample_count: 12,
      valid_count: 12,
      errors: [],
      warnings: [],
      length_stats: { min_chars: 8, max_chars: 120, avg_chars: 42 },
      recommended_target_format: 'openai_messages',
      health: {
        json_valid_ratio: 1,
        field_completeness: 1,
        overlong_sample_ratio: 0,
        duplicate_sample_ratio: 0,
      },
    });
    mockPreviewDataset.mockResolvedValue({ total_samples: 12, preview: [{ question: '你好', answer: '你好' }] });
    mockTransformDataset.mockResolvedValue({ dataset_id: 'dataset-1', sample_count: 12 });
    mockSplitDataset.mockResolvedValue({ dataset_id: 'dataset-1' });
    mockDeleteDataset.mockResolvedValue({ message: 'ok' });
    mockUploadDataset.mockResolvedValue({ id: 'dataset-2', name: '新数据集' });

    mockGetTrainingStatus.mockResolvedValue({
      is_training: false,
      progress: null,
    });
    mockCheckTrainingResources.mockResolvedValue({
      passed: true,
      available_vram: 8,
      required_vram: 4,
      suggestions: [],
      warnings: [],
      recommended_config: {},
      device_name: 'Mock GPU',
    });
    mockGetTrainingFailureAnalytics.mockResolvedValue({
      totalRuns: 0,
      failedRuns: 0,
      stoppedRuns: 0,
      completedRuns: 0,
      failureRate: 0,
      failureRate7d: 0,
      failureRate14d: 0,
      failedRuns7d: 0,
      failedRuns14d: 0,
      totalRuns7d: 0,
      totalRuns14d: 0,
      suspectedVramPressureCount: 0,
      longContextFailureCount: 0,
      unquantizedFailureCount: 0,
      topFailedModels: [],
      topFailedDatasets: [],
      topFailedMethods: [],
      recentFailures: [],
    });
    mockGetTrainingHistory.mockResolvedValue([]);
    mockGetTrainingCheckpoints.mockResolvedValue([]);
    mockGetTrainingRecoveryOptions.mockResolvedValue({
      generatedAt: new Date().toISOString(),
      options: [],
    });
    mockGetTrainingOverviewV2.mockResolvedValue({
      queue: { queue_size: 0, running_count: 0, max_queue_size: 4 },
      resource_signals: {
        suspected_vram_pressure_count: 0,
        long_context_failure_count: 0,
        unquantized_failure_count: 0,
      },
    });
    mockResumeTraining.mockResolvedValue({
      id: 'resume-task-1',
      modelName: 'mock-model',
      datasetName: 'mock-dataset',
      status: 'running',
      method: 'qlora',
      startTime: new Date().toISOString(),
      outputPath: '/tmp/output',
      config: {},
    });

    mockGetBackends.mockResolvedValue({
      current: 'ollama',
      backends: [
        { id: 'ollama', name: 'Ollama', available: false },
        { id: 'huggingface', name: 'HuggingFace', available: true },
      ],
    });
    mockGetModelList.mockResolvedValue([{ id: 'base-model', name: '基础模型' }]);
    mockGetInferenceModels.mockResolvedValue([{ id: 'hf-model', name: 'HF Model' }]);
    mockCreateEvaluationRun.mockResolvedValue({
      run_id: 'eval-1',
      scenario: 'qa_assistant',
      base_model: 'base-model',
      finetuned_model: 'outputs/train-1/merged',
      adapter_path: 'outputs/train-1/adapter',
      base_outputs: ['基础回答'],
      finetuned_outputs: ['微调回答'],
      cases: [{ prompt: '你好', base_output: '基础回答', finetuned_output: '微调回答' }],
      metrics: { human_score_count: 0, good_rate: 0 },
      failed_cases: [],
      human_scores: {},
    });
    mockScoreEvaluationCase.mockResolvedValue({ ok: true });
    mockListDeploymentPackages.mockResolvedValue([
      {
        package_id: 'deploy-1',
        training_task_id: 'train-1',
        created_at: new Date().toISOString(),
        base_model: 'base-model',
        adapter_path: 'outputs/train-1/adapter',
        model_name: 'qa-assistant',
      },
    ]);
    mockCreateDeploymentPackage.mockResolvedValue({
      package_id: 'deploy-1',
      training_task_id: 'train-1',
      base_model: 'base-model',
      adapter_path: 'outputs/train-1/adapter',
      merged_model_path: 'outputs/train-1/merged',
      ollama_modelfile: 'FROM base-model',
      openai_compatible_examples: {
        curl: 'curl http://127.0.0.1:8000/v1/chat/completions',
        Python: 'print("ok")',
        TypeScript: 'console.log("ok")',
      },
      env_template: {
        OPENAI_BASE_URL: 'http://127.0.0.1:8000/v1',
        MODEL_NAME: 'qa-assistant',
      },
    });
    mockGetDeploymentPackage.mockResolvedValue({
      package_id: 'deploy-1',
      training_task_id: 'train-1',
      base_model: 'base-model',
      adapter_path: 'outputs/train-1/adapter',
      openai_compatible_examples: {},
      env_template: {},
    });
    mockDeleteDeploymentPackage.mockResolvedValue({ ok: true });
    mockGetOllamaStatus.mockResolvedValue({ models: [] });
    mockListInferenceEngines.mockResolvedValue({ engines: [] });
    mockGetPerformanceStats.mockResolvedValue({
      inference: { total_requests: 0, avg_latency_ms: 0 },
      streaming: { avg_first_token_ms: 0 },
    });
    mockGetPerformanceRecommendations.mockResolvedValue({ recommendations: [] });
    mockGetSavedCloudProviders.mockResolvedValue({ keys: [] });
    mockGetSavedCloudProviderData.mockResolvedValue({});
    mockGetPrimaryAgents.mockResolvedValue([]);

    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/knowledge/embedder/status')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ loaded: false, error: 'unavailable' }),
        });
      }
      if (url.includes('/knowledge/collections')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ collections: [] }),
        });
      }
      if (url.includes('/knowledge/collections/default')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ name: 'default', count: 0, documents: [] }),
        });
      }
      if (url.includes('/cloud/api-keys')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ keys: [] }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });
  });

  it('renders disconnected training empty state', async () => {
    mockUseAppStore.mockReturnValue({
      models: [],
      datasets: [],
      backendStatus: 'disconnected',
      isTraining: false,
      setIsTraining: vi.fn(),
      addTrainingRecord: vi.fn(),
      setModels: vi.fn(),
    });

    renderWithRouter(<TrainingPage />);

    await waitFor(() => {
      expect(screen.getByText('后端服务未连接，请先启动应用。')).toBeInTheDocument();
    });
  });

  it('prefills training configuration from product-chain query params', async () => {
    renderWithRouter(
      <TrainingPage />,
      ['/training?model_id=base-model&dataset_id=dataset-1&task_goal=structured_extraction'],
    );

    expect(screen.getByText('模型训练')).toBeInTheDocument();
    expect(screen.getByText('控制台')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockSetTrainingSelection).toHaveBeenLastCalledWith({
        modelId: 'base-model',
        datasetId: 'dataset-1',
      });
    });
  });

  it('renders inference backend warning when ollama is unavailable', async () => {
    renderWithRouter(<Inference />);

    expect(screen.getByText('推理测试')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText('Ollama 未运行').length).toBeGreaterThan(0);
      expect(screen.getByText('请确保 Ollama 已启动，然后刷新页面')).toBeInTheDocument();
    });
  });

  it('renders knowledge embedder warning state', async () => {
    renderWithRouter(<KnowledgeBase />);

    expect(screen.getByText('RAG 知识库')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('嵌入模型未加载')).toBeInTheDocument();
      expect(screen.getAllByText('立即加载').length).toBeGreaterThan(0);
    });
  });

  it('renders chat shell and loads primary init resources', async () => {
    renderWithRouter(<ChatPage />);

    expect(screen.getByText('Mock Chat Header')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockLoadSessions).toHaveBeenCalled();
      expect(mockGetSavedCloudProviders).toHaveBeenCalled();
    });
  });

  it('renders dashboard product chain health and primary routes', async () => {
    renderWithRouter(<Dashboard />);

    expect(screen.getByText('运行中控台')).toBeInTheDocument();
    expect(screen.getByText('工程闭环健康')).toBeInTheDocument();
    expect(screen.getByText('主要操作入口')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('存储健康')).toBeInTheDocument();
      expect(screen.getByText('正常')).toBeInTheDocument();
      expect(screen.getByText('评估与部署')).toBeInTheDocument();
    });
  });

  it('renders dataset workbench and opens analysis actions', async () => {
    renderWithRouter(<DatasetManager />);

    expect(screen.getByText('数据准备中心')).toBeInTheDocument();
    expect(screen.getByText('点击或拖拽上传 JSON / JSONL 数据集')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('客服问答集')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /分析/ }));
    await waitFor(() => {
      expect(mockAnalyzeDataset).toHaveBeenCalledWith('dataset-1');
      expect(screen.getByText('导出训练 JSONL')).toBeInTheDocument();
      expect(screen.getByText('进入训练配置')).toBeInTheDocument();
    });
  });

  it('renders evaluation page from training query params', async () => {
    renderWithRouter(
      <Evaluation />,
      ['/evaluation?scenario=qa_assistant&base_model=base-model&test_dataset_id=dataset-1&training_task_id=train-1&run_inference=true'],
    );

    expect(screen.getByText('评估实验室')).toBeInTheDocument();
    expect(screen.getByText('当前评估对象')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByDisplayValue('base-model')).toBeInTheDocument();
      expect(screen.getByText('真实推理')).toBeInTheDocument();
      expect(screen.getAllByText('客服/知识问答助手').length).toBeGreaterThan(0);
    });
  });

  it('renders deployment page with package history and query param prefill', async () => {
    renderWithRouter(
      <Deployment />,
      ['/deployment?training_task_id=train-1&base_model=base-model&adapter_path=outputs/train-1/adapter&model_alias=qa-assistant'],
    );

    expect(screen.getByText('部署接入台')).toBeInTheDocument();
    expect(screen.getAllByText('生成部署包').length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByDisplayValue('train-1')).toBeInTheDocument();
      expect(screen.getByDisplayValue('base-model')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('最近部署包')).toBeInTheDocument();
      expect(screen.getByText('qa-assistant')).toBeInTheDocument();
    });
  });
});
