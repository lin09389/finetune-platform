import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetModelRuntimeOverview = vi.hoisted(() => vi.fn());
const mockSetModelRuntimeSelection = vi.hoisted(() => vi.fn());
const mockDownloadModelFromModelScope = vi.hoisted(() => vi.fn());
const mockDownloadModelFromHuggingFace = vi.hoisted(() => vi.fn());
const mockGetDownloadProgress = vi.hoisted(() => vi.fn());
const mockImportModelFromModelScope = vi.hoisted(() => vi.fn());
const mockDeleteLocalModel = vi.hoisted(() => vi.fn());
const mockSearchModels = vi.hoisted(() => vi.fn());
const mockSyncInferenceSelection = vi.hoisted(() => vi.fn());
const mockSetInferenceSelection = vi.hoisted(() => vi.fn());
const mockNavigate = vi.hoisted(() => vi.fn());

vi.mock('../services/api', () => ({
  getModelRuntimeOverview: mockGetModelRuntimeOverview,
  setModelRuntimeSelection: mockSetModelRuntimeSelection,
  downloadModelFromModelScope: mockDownloadModelFromModelScope,
  downloadModelFromHuggingFace: mockDownloadModelFromHuggingFace,
  getDownloadProgress: mockGetDownloadProgress,
  importModelFromModelScope: mockImportModelFromModelScope,
  deleteLocalModel: mockDeleteLocalModel,
  searchModels: mockSearchModels,
  extractApiErrorMessage: (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback,
}));

vi.mock('../runtime/RuntimeContext', () => ({
  useRuntimeContext: () => ({
    actions: {
      setInferenceSelection: mockSetInferenceSelection,
      syncInferenceSelection: mockSyncInferenceSelection,
    },
  }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import ModelRuntimeCenter from '../pages/ModelRuntimeCenter';

const readyOverview = {
  schema_version: 'model.runtime.overview.v1',
  generated_at: '2026-06-25T00:00:00',
  summary: {
    state: 'ready',
    headline: 'Agent 和本地对话已就绪',
    total_models: 2,
    agent_ready_models: 1,
    local_ready_models: 2,
    ollama_available: true,
  },
  active_selection: {
    backend: 'ollama',
    model_id: 'qwen2.5:7b',
    scope: 'agent',
  },
  agent: {
    ready: true,
    provider: 'ollama',
    model: 'qwen2.5:7b',
    model_string: 'ollama:qwen2.5:7b',
    message: 'Agent Workbench 会优先使用该 Ollama 模型。',
  },
  backends: [
    { id: 'huggingface', name: 'HuggingFace', available: true },
    { id: 'ollama', name: 'Ollama', available: true },
  ],
  local_models: [
    {
      id: 'qwen2.5:7b',
      name: 'qwen2.5:7b',
      backend: 'ollama',
      source: 'ollama',
      path: null,
      size: 4000000000,
      size_label: '3.7 GB',
      capabilities: ['agent', 'chat', 'inference'],
      readiness: {
        state: 'ready',
        label: 'Agent 就绪',
        message: '可直接作为 Agent Workbench 的默认模型。',
        fix_action: null,
      },
      recommended_for: ['agent', 'chat'],
      metadata: {},
    },
    {
      id: 'Qwen2.5-0.5B-Instruct',
      name: 'Qwen2.5 0.5B',
      backend: 'huggingface',
      source: 'local',
      path: 'C:/models/Qwen2.5-0.5B-Instruct',
      size: 1000000000,
      size_label: '953.7 MB',
      capabilities: ['chat', 'evaluation', 'fine_tune', 'inference'],
      readiness: {
        state: 'ready',
        label: '本地推理就绪',
        message: '可用于推理、评估或训练链路。',
        fix_action: null,
      },
      recommended_for: ['chat', 'fine_tune', 'evaluation'],
      metadata: {},
    },
  ],
  recommended_models: [
    {
      repo_id: 'Qwen/Qwen2.5-0.5B-Instruct',
      name: 'Qwen2.5 0.5B',
      description: '轻量中文对话模型',
      size: '~1GB',
      source: 'modelscope',
      category: 'chat',
      fit: 'best',
      why: '适合当前设备的 INT4 / 低显存优先策略。',
    },
  ],
  quick_actions: [],
  environment: {
    models_dir: 'C:/models',
    model_source: 'modelscope',
    ollama_base_url: 'http://localhost:11434',
    hardware_profile: { profile: 'low_vram' },
  },
  diagnostics: [],
};

const renderCenter = () =>
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App>
        <ModelRuntimeCenter />
      </App>
    </MemoryRouter>,
  );

describe('ModelRuntimeCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetModelRuntimeOverview.mockResolvedValue(readyOverview);
    mockSetModelRuntimeSelection.mockResolvedValue({
      selected: { backend: 'ollama', model_id: 'qwen2.5:7b', scope: 'agent' },
    });
  });

  it('renders an Agent-first model runtime overview', async () => {
    renderCenter();

    expect(await screen.findByText('Agent 和本地对话已就绪')).toBeInTheDocument();
    expect(screen.getByText('ollama:qwen2.5:7b')).toBeInTheDocument();
    expect(screen.getByText('Agent 就绪')).toBeInTheDocument();
    expect(mockSetInferenceSelection).toHaveBeenCalledWith({
      backend: 'ollama',
      modelId: 'qwen2.5:7b',
    });
  });

  it('syncs selected Agent model into runtime context', async () => {
    renderCenter();

    await screen.findByText('qwen2.5:7b');
    const agentButtons = screen.getAllByRole('button', { name: /Agent$/ });
    expect(agentButtons[0]).toBeDefined();
    fireEvent.click(agentButtons[0]!);

    await waitFor(() => {
      expect(mockSetModelRuntimeSelection).toHaveBeenCalledWith({
        backend: 'ollama',
        model_id: 'qwen2.5:7b',
        scope: 'agent',
      });
      expect(mockSyncInferenceSelection).toHaveBeenCalledWith({
        backend: 'ollama',
        modelId: 'qwen2.5:7b',
      });
    });
  }, 15000);

  it('starts a recommended ModelScope download from the discover tab', async () => {
    mockDownloadModelFromModelScope.mockResolvedValue({ task_id: 'download_1' });
    mockGetDownloadProgress.mockResolvedValue({
      task_id: 'download_1',
      status: 'completed',
      progress: 100,
    });

    renderCenter();

    fireEvent.click(await screen.findByRole('tab', { name: '获取模型' }));
    const downloadButtons = await screen.findAllByRole('button', { name: /下载$/ });
    fireEvent.click(downloadButtons[0]!);

    await waitFor(() => {
      expect(mockDownloadModelFromModelScope).toHaveBeenCalledWith('Qwen/Qwen2.5-0.5B-Instruct');
    });
  }, 15000);
});
