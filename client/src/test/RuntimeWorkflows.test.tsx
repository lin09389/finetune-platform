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

const WorkflowActors: React.FC = () => {
  const runtime = useRuntimeContext();
  const [, rerenderActor] = React.useState(0);

  return (
    <div>
      <div data-testid="active-backend">{runtime.derived.activeBackend}</div>
      <div data-testid="active-model">{runtime.derived.activeModelId || 'none'}</div>
      <div data-testid="active-collection">{runtime.derived.activeKnowledgeCollection}</div>
      <div data-testid="selected-training-model">{runtime.selected.training.modelId || 'none'}</div>
      <div data-testid="selected-inference-model">
        {runtime.selected.inference.modelId || 'none'}
      </div>
      <div data-testid="selected-collection">
        {runtime.selected.knowledge.collectionId || 'none'}
      </div>

      <button
        onClick={() => runtime.actions.setTrainingSelection({ modelId: 'training-base-model' })}
      >
        training-select-model
      </button>
      <button
        onClick={() =>
          runtime.actions.syncInferenceSelection({
            backend: 'huggingface',
            modelId: runtime.selected.training.modelId,
          })
        }
      >
        training-promote-model
      </button>
      <button onClick={() => runtime.actions.syncKnowledgeCollection('project-docs')}>
        knowledge-select-project-docs
      </button>
      <button
        onClick={() => {
          chatState.settings = {
            ...chatState.settings,
            backend: 'ollama',
            modelId: 'chat-picked-ollama',
            knowledgeCollection: 'chat-picked-docs',
          };
          rerenderActor((value) => value + 1);
        }}
      >
        chat-pick-runtime
      </button>
    </div>
  );
};

const renderWorkflow = () =>
  render(
    <RuntimeContextProvider>
      <WorkflowActors />
    </RuntimeContextProvider>,
  );

describe('Runtime cross-page workflows', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAppStore.mockReturnValue({
      backendStatus: 'connected',
    });

    chatState = {
      settings: {
        modelId: '',
        backend: 'huggingface',
        useKnowledge: false,
        knowledgeCollection: undefined,
        useMemory: false,
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
        { id: 'ollama', name: 'Ollama', available: true, description: '外部服务' },
      ],
    });

    mockGetInferenceModels.mockResolvedValue([
      { id: 'hf-default', name: 'HF Default' },
      { id: 'training-base-model', name: 'Training Base Model' },
    ]);

    mockGetOllamaStatus.mockResolvedValue({
      available: true,
      models: [{ name: 'chat-picked-ollama' }],
    });
    mockGetRuntimeBootstrap.mockRejectedValue(new Error('bootstrap disabled in workflow tests'));

    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/knowledge/collections')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              collections: [
                { name: 'default', count: 0 },
                { name: 'project-docs', count: 12 },
                { name: 'chat-picked-docs', count: 7 },
              ],
            }),
        });
      }

      if (url.includes('/knowledge/embedder/status')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              loaded: true,
              model_name: 'text2vec-base-chinese',
              dimension: 768,
            }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      });
    });
  });

  it('propagates a training-selected model into the active inference context', async () => {
    renderWorkflow();

    fireEvent.click(screen.getByText('training-select-model'));

    await waitFor(() => {
      expect(screen.getByTestId('selected-training-model')).toHaveTextContent(
        'training-base-model',
      );
      expect(screen.getByTestId('active-model')).toHaveTextContent('training-base-model');
    });

    fireEvent.click(screen.getByText('training-promote-model'));

    await waitFor(() => {
      expect(mockUpdateChatSettings).toHaveBeenCalledWith({
        backend: 'huggingface',
        modelId: 'training-base-model',
      });
      expect(screen.getByTestId('selected-inference-model')).toHaveTextContent(
        'training-base-model',
      );
      expect(screen.getByTestId('active-backend')).toHaveTextContent('huggingface');
    });
  });

  it('propagates knowledge collection changes into chat runtime settings', async () => {
    renderWorkflow();

    fireEvent.click(screen.getByText('knowledge-select-project-docs'));

    await waitFor(() => {
      expect(mockUpdateChatSettings).toHaveBeenCalledWith({ knowledgeCollection: 'project-docs' });
      expect(screen.getByTestId('selected-collection')).toHaveTextContent('project-docs');
      expect(screen.getByTestId('active-collection')).toHaveTextContent('project-docs');
    });
  });

  it('reflects chat-selected backend, model, and collection in the runtime summary', async () => {
    renderWorkflow();

    fireEvent.click(screen.getByText('chat-pick-runtime'));

    await waitFor(() => {
      expect(screen.getByTestId('active-backend')).toHaveTextContent('ollama');
      expect(screen.getByTestId('active-model')).toHaveTextContent('chat-picked-ollama');
      expect(screen.getByTestId('active-collection')).toHaveTextContent('chat-picked-docs');
    });
  });
});
