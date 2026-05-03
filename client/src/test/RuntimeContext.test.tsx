import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockUseAppStore = vi.hoisted(() => vi.fn());
const mockUseChatStore = vi.hoisted(() => vi.fn());
const mockGetBackends = vi.hoisted(() => vi.fn());
const mockGetInferenceModels = vi.hoisted(() => vi.fn());
const mockGetOllamaStatus = vi.hoisted(() => vi.fn());
const mockGetRuntimeBootstrap = vi.hoisted(() => vi.fn());
const mockFetch = vi.hoisted(() => vi.fn());
const mockUpdateChatSettings = vi.hoisted(() => vi.fn());

vi.stubGlobal('fetch', mockFetch);

vi.mock('../store/appStore', () => ({
  useAppStore: mockUseAppStore,
}));

vi.mock('../store/chatStore', () => ({
  useChatStore: mockUseChatStore,
}));

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
  getBackends: mockGetBackends,
  getInferenceModels: mockGetInferenceModels,
  getOllamaStatus: mockGetOllamaStatus,
  getRuntimeBootstrap: mockGetRuntimeBootstrap,
}));

import { RuntimeContextProvider, useRuntimeContext } from '../runtime/RuntimeContext';

type MockChatState = {
  settings: {
    modelId: string;
    backend: 'ollama' | 'huggingface' | 'cloud';
    useKnowledge: boolean;
    knowledgeCollection?: string;
    useMemory: boolean;
  };
  updateSettings: typeof mockUpdateChatSettings;
};

let chatState: MockChatState;
let appBackendStatus: 'connected' | 'disconnected' | 'checking';

const RuntimeProbe: React.FC = () => {
  const runtime = useRuntimeContext();

  return (
    <div>
      <div data-testid="runtime-status">{runtime.summary.runtimeStatus}</div>
      <div data-testid="runtime-backend">{runtime.summary.activeBackend}</div>
      <div data-testid="runtime-model">{runtime.summary.activeModelId || 'none'}</div>
      <div data-testid="runtime-collection">{runtime.summary.activeKnowledgeCollection}</div>
      <div data-testid="runtime-model-count">{String(runtime.inference.availableModelCount)}</div>
      <div data-testid="runtime-warning-count">{String(runtime.summary.warnings.length)}</div>
      <div data-testid="runtime-training-phase">{runtime.derived.trainingSignal.phase}</div>
      <div data-testid="runtime-training-label">{runtime.derived.trainingSignal.label}</div>
      <div data-testid="observed-backend-status">{runtime.observed.backendStatus}</div>
      <div data-testid="observed-backend-count">
        {String(runtime.observed.inference.backends.length)}
      </div>
      <div data-testid="selected-inference-model">
        {runtime.selected.inference.modelId || 'none'}
      </div>
      <div data-testid="derived-model-count">{String(runtime.derived.availableModelCount)}</div>
      <div data-testid="derived-runtime-status">{runtime.derived.runtimeStatus}</div>
      <button
        onClick={() => runtime.setInferenceSelection({ backend: 'ollama', modelId: 'llama3:8b' })}
      >
        set-inference
      </button>
      <button
        onClick={() =>
          runtime.actions.setInferenceSelection({ backend: 'ollama', modelId: 'action-llama' })
        }
      >
        action-set-inference
      </button>
      <button onClick={() => runtime.actions.refreshBootstrap()}>refresh-bootstrap</button>
      <button
        onClick={() =>
          runtime.syncInferenceSelection({ backend: 'ollama', modelId: 'shared-ollama' })
        }
      >
        sync-inference
      </button>
      <button onClick={() => runtime.actions.syncKnowledgeCollection('action-sync-docs')}>
        action-sync-knowledge
      </button>
      <button onClick={() => runtime.setKnowledgeSelection({ collectionId: 'project-docs' })}>
        set-knowledge
      </button>
      <button onClick={() => runtime.syncKnowledgeCollection('shared-sync-docs')}>
        sync-knowledge
      </button>
    </div>
  );
};

const RuntimePropagationHarness: React.FC = () => {
  const runtime = useRuntimeContext();

  return (
    <div>
      <RuntimeProbe />
      <button onClick={() => runtime.setKnowledgeSelection({ collectionId: undefined })}>
        clear-knowledge-override
      </button>
      <button
        onClick={() => runtime.setInferenceSelection({ backend: undefined, modelId: undefined })}
      >
        clear-inference-override
      </button>
      <button onClick={() => runtime.setTrainingSelection({ modelId: 'train-model' })}>
        set-training-model
      </button>
    </div>
  );
};

const RuntimeProviderHarness: React.FC = () => {
  const [, setVersion] = React.useState(0);

  return (
    <div>
      <button
        onClick={() => {
          chatState.settings = {
            ...chatState.settings,
            backend: 'ollama',
            modelId: 'chat-ollama',
            knowledgeCollection: 'chat-knowledge',
          };
          setVersion((value) => value + 1);
        }}
      >
        mutate-chat-settings
      </button>
      <button
        onClick={() => {
          chatState.settings = {
            ...chatState.settings,
            modelId: '',
          };
          setVersion((value) => value + 1);
        }}
      >
        clear-chat-model
      </button>
      <RuntimeContextProvider>
        <RuntimePropagationHarness />
      </RuntimeContextProvider>
    </div>
  );
};

const RuntimeBackendStatusHarness: React.FC = () => {
  const [, setVersion] = React.useState(0);

  return (
    <div>
      <button
        onClick={() => {
          appBackendStatus = 'disconnected';
          setVersion((value) => value + 1);
        }}
      >
        disconnect-backend
      </button>
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>
    </div>
  );
};

describe('RuntimeContextProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    appBackendStatus = 'connected';
    mockUseAppStore.mockImplementation(() => ({
      backendStatus: appBackendStatus,
    }));

    chatState = {
      settings: {
        modelId: 'hf-default',
        backend: 'huggingface',
        useKnowledge: true,
        knowledgeCollection: 'team-docs',
        useMemory: true,
      },
      updateSettings: mockUpdateChatSettings,
    };

    mockUseChatStore.mockImplementation((selector?: (state: MockChatState) => unknown) =>
      selector ? selector(chatState) : chatState,
    );

    mockGetBackends.mockResolvedValue({
      current: 'huggingface',
      backends: [
        { id: 'huggingface', name: 'HuggingFace', available: true, description: '本地模型' },
        { id: 'ollama', name: 'Ollama', available: false, description: '外部服务' },
      ],
    });

    mockGetInferenceModels.mockResolvedValue([
      { id: 'hf-default', name: 'HF Default' },
      { id: 'hf-alt', name: 'HF Alt' },
    ]);

    mockGetOllamaStatus.mockResolvedValue({
      available: false,
      models: [{ name: 'llama3:8b' }],
    });
    mockGetRuntimeBootstrap.mockRejectedValue(new Error('bootstrap disabled in legacy tests'));

    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/knowledge/collections')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              collections: [
                { name: 'team-docs', count: 6 },
                { name: 'project-docs', count: 3 },
              ],
            }),
        });
      }

      if (url.includes('/knowledge/embedder/status')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              loaded: false,
              error: 'dependency_missing',
            }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });
  });

  it('aggregates backend, model, and knowledge truth into a degraded runtime summary', async () => {
    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('runtime-status')).toHaveTextContent('degraded');
      expect(screen.getByTestId('runtime-backend')).toHaveTextContent('huggingface');
      expect(screen.getByTestId('runtime-model')).toHaveTextContent('hf-default');
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('team-docs');
      expect(screen.getByTestId('runtime-model-count')).toHaveTextContent('2');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('1');
      expect(screen.getByTestId('observed-backend-status')).toHaveTextContent('connected');
      expect(screen.getByTestId('observed-backend-count')).toHaveTextContent('2');
      expect(screen.getByTestId('derived-model-count')).toHaveTextContent('2');
      expect(screen.getByTestId('derived-runtime-status')).toHaveTextContent('degraded');
    });
  });

  it('uses runtime bootstrap as the primary initialization path when available', async () => {
    mockGetRuntimeBootstrap.mockResolvedValue({
      schema_version: 'runtime.bootstrap.v1',
      generated_at: '2026-04-16T00:00:00',
      observed: {
        backend_status: 'connected',
        inference: {
          current_backend: 'ollama',
          backends: [
            { id: 'huggingface', name: 'HuggingFace', available: true },
            { id: 'ollama', name: 'Ollama', available: true },
          ],
          huggingface_models: [{ id: 'hf-bootstrap', name: 'HF Bootstrap' }],
          ollama: {
            available: true,
            running: true,
            base_url: 'http://localhost:11434',
            models: [{ id: 'ollama-bootstrap', name: 'Ollama Bootstrap' }],
          },
        },
        knowledge: {
          collections: [{ id: 'bootstrap-docs', name: 'bootstrap-docs', count: 9 }],
          embedder_status: { loaded: true, model_name: 'text2vec', dimension: 768 },
        },
        training: { is_training: false },
      },
      derived: {
        runtime_status: 'ready',
        warnings: [],
        available_model_count: 1,
      },
    });

    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('runtime-backend')).toHaveTextContent('huggingface');
      expect(screen.getByTestId('observed-backend-count')).toHaveTextContent('2');
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('team-docs');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('0');
    });

    expect(mockGetRuntimeBootstrap).toHaveBeenCalled();
    expect(mockGetBackends).not.toHaveBeenCalled();
    expect(mockGetInferenceModels).not.toHaveBeenCalled();
    expect(mockGetOllamaStatus).not.toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('preserves server-derived bootstrap warnings in the shared runtime summary', async () => {
    mockGetRuntimeBootstrap.mockResolvedValue({
      schema_version: 'runtime.bootstrap.v1',
      generated_at: '2026-04-16T00:00:00',
      observed: {
        backend_status: 'connected',
        inference: {
          current_backend: 'huggingface',
          backends: [{ id: 'huggingface', name: 'HuggingFace', available: true }],
          huggingface_models: [{ id: 'hf-bootstrap', name: 'HF Bootstrap' }],
          ollama: {
            available: false,
            running: false,
            base_url: 'http://localhost:11434',
            models: [],
          },
        },
        knowledge: {
          collections: [{ id: 'team-docs', name: 'team-docs', count: 9 }],
          embedder_status: { loaded: true, model_name: 'text2vec', dimension: 768 },
        },
        training: { is_training: false },
      },
      derived: {
        runtime_status: 'degraded',
        warnings: ['training.status: worker timeout'],
        available_model_count: 1,
      },
    });

    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('runtime-status')).toHaveTextContent('degraded');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('1');
      expect(screen.getByTestId('derived-runtime-status')).toHaveTextContent('degraded');
    });
  });

  it('maps failed training progress status into runtime warning and phase signal', async () => {
    mockGetRuntimeBootstrap.mockResolvedValue({
      schema_version: 'runtime.bootstrap.v1',
      generated_at: '2026-04-16T00:00:00',
      observed: {
        backend_status: 'connected',
        inference: {
          current_backend: 'huggingface',
          backends: [{ id: 'huggingface', name: 'HuggingFace', available: true }],
          huggingface_models: [{ id: 'hf-bootstrap', name: 'HF Bootstrap' }],
          ollama: {
            available: false,
            running: false,
            base_url: 'http://localhost:11434',
            models: [],
          },
        },
        knowledge: {
          collections: [{ id: 'team-docs', name: 'team-docs', count: 9 }],
          embedder_status: { loaded: true, model_name: 'text2vec', dimension: 768 },
        },
        training: {
          is_training: false,
          progress: {
            status: 'failed',
            message: 'CUDA OOM on step 120',
          },
        },
      },
      derived: {
        runtime_status: 'ready',
        warnings: [],
        available_model_count: 1,
      },
    });

    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('runtime-status')).toHaveTextContent('degraded');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('1');
      expect(screen.getByTestId('runtime-training-phase')).toHaveTextContent('failed');
      expect(screen.getByTestId('runtime-training-label')).toHaveTextContent('训练失败');
    });
  });

  it('clears stale bootstrap warnings after backend disconnects', async () => {
    mockGetRuntimeBootstrap.mockResolvedValue({
      schema_version: 'runtime.bootstrap.v1',
      generated_at: '2026-04-16T00:00:00',
      observed: {
        backend_status: 'connected',
        inference: {
          current_backend: 'huggingface',
          backends: [{ id: 'huggingface', name: 'HuggingFace', available: true }],
          huggingface_models: [{ id: 'hf-bootstrap', name: 'HF Bootstrap' }],
          ollama: {
            available: false,
            running: false,
            base_url: 'http://localhost:11434',
            models: [],
          },
        },
        knowledge: {
          collections: [{ id: 'team-docs', name: 'team-docs', count: 9 }],
          embedder_status: { loaded: true, model_name: 'text2vec', dimension: 768 },
        },
        training: { is_training: false },
      },
      derived: {
        runtime_status: 'degraded',
        warnings: ['training.status: worker timeout'],
        available_model_count: 1,
      },
    });

    render(<RuntimeBackendStatusHarness />);

    await waitFor(() => {
      expect(screen.getByTestId('runtime-status')).toHaveTextContent('degraded');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('1');
    });

    fireEvent.click(screen.getByText('disconnect-backend'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-status')).toHaveTextContent('offline');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('1');
    });
  });

  it('lets page-level selections override shared runtime defaults', async () => {
    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('runtime-backend')).toHaveTextContent('huggingface');
    });

    fireEvent.click(screen.getByText('set-inference'));
    fireEvent.click(screen.getByText('set-knowledge'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-backend')).toHaveTextContent('ollama');
      expect(screen.getByTestId('runtime-model')).toHaveTextContent('llama3:8b');
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('project-docs');
      expect(screen.getByTestId('runtime-model-count')).toHaveTextContent('1');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('2');
    });
  });

  it('syncs knowledge selection back into chat settings through the shared runtime API', async () => {
    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    fireEvent.click(screen.getByText('sync-knowledge'));

    await waitFor(() => {
      expect(mockUpdateChatSettings).toHaveBeenCalledWith({
        knowledgeCollection: 'shared-sync-docs',
      });
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('shared-sync-docs');
    });
  });

  it('syncs inference selection back into chat settings through the shared runtime API', async () => {
    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    fireEvent.click(screen.getByText('sync-inference'));

    await waitFor(() => {
      expect(mockUpdateChatSettings).toHaveBeenCalledWith({
        backend: 'ollama',
        modelId: 'shared-ollama',
      });
      expect(screen.getByTestId('runtime-backend')).toHaveTextContent('ollama');
      expect(screen.getByTestId('runtime-model')).toHaveTextContent('shared-ollama');
      expect(screen.getByTestId('runtime-model-count')).toHaveTextContent('1');
    });
  });

  it('exposes grouped runtime actions that match legacy selection and sync behavior', async () => {
    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    fireEvent.click(screen.getByText('action-set-inference'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-model')).toHaveTextContent('action-llama');
      expect(screen.getByTestId('selected-inference-model')).toHaveTextContent('action-llama');
    });

    fireEvent.click(screen.getByText('action-sync-knowledge'));

    await waitFor(() => {
      expect(mockUpdateChatSettings).toHaveBeenCalledWith({
        knowledgeCollection: 'action-sync-docs',
      });
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('action-sync-docs');
    });
  });

  it('stays offline and skips remote refresh when backend is disconnected', async () => {
    mockUseAppStore.mockReturnValue({
      backendStatus: 'disconnected',
    });

    render(
      <RuntimeContextProvider>
        <RuntimeProbe />
      </RuntimeContextProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('runtime-status')).toHaveTextContent('offline');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('2');
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('team-docs');
    });

    expect(mockGetBackends).not.toHaveBeenCalled();
    expect(mockGetInferenceModels).not.toHaveBeenCalled();
    expect(mockGetOllamaStatus).not.toHaveBeenCalled();
    expect(mockGetRuntimeBootstrap).not.toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('propagates chat state changes through runtime summary until page overrides are cleared', async () => {
    render(<RuntimeProviderHarness />);

    await waitFor(() => {
      expect(screen.getByTestId('runtime-backend')).toHaveTextContent('huggingface');
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('team-docs');
    });

    fireEvent.click(screen.getByText('set-knowledge'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('project-docs');
    });

    fireEvent.click(screen.getByText('mutate-chat-settings'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-backend')).toHaveTextContent('ollama');
      expect(screen.getByTestId('runtime-model')).toHaveTextContent('chat-ollama');
      expect(screen.getByTestId('runtime-model-count')).toHaveTextContent('1');
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('project-docs');
      expect(screen.getByTestId('runtime-warning-count')).toHaveTextContent('2');
    });

    fireEvent.click(screen.getByText('clear-knowledge-override'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-collection')).toHaveTextContent('chat-knowledge');
    });
  });

  it('falls back from cleared inference/chat model selection to training model', async () => {
    render(<RuntimeProviderHarness />);

    fireEvent.click(screen.getByText('set-inference'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-model')).toHaveTextContent('llama3:8b');
    });

    fireEvent.click(screen.getByText('clear-inference-override'));
    fireEvent.click(screen.getByText('clear-chat-model'));
    fireEvent.click(screen.getByText('set-training-model'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-model')).toHaveTextContent('train-model');
      expect(screen.getByTestId('runtime-backend')).toHaveTextContent('huggingface');
    });
  });
});
