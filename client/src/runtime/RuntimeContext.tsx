import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  API_BASE_URL,
  getBackends,
  getInferenceModels,
  getOllamaStatus,
  getRuntimeBootstrap,
  type RuntimeBootstrapPayload,
} from '../services/api';
import { useAppStore } from '../store/appStore';
import { useChatStore } from '../store/chatStore';

export interface RuntimeModelOption {
  id: string;
  name: string;
}

export interface RuntimeBackendInfo {
  id: string;
  name: string;
  available: boolean;
  description?: string;
}

export interface RuntimeCollection {
  id: string;
  name: string;
  count: number;
}

export interface RuntimeEmbedderStatus {
  loaded: boolean;
  model_name?: string;
  dimension?: number;
  error?: string;
}

export type RuntimeTrainingPhase =
  | 'idle'
  | 'loading'
  | 'training'
  | 'running'
  | 'stopping'
  | 'stopped'
  | 'completed'
  | 'failed';

export interface RuntimeTrainingObserved {
  isTraining: boolean;
  progressStatus: RuntimeTrainingPhase;
  progressMessage?: string;
}

export interface RuntimeTrainingSignal {
  phase: RuntimeTrainingPhase;
  label: string;
  tone: 'success' | 'warning' | 'error' | 'info';
}

export interface RuntimeSelectionState {
  training: {
    modelId?: string;
    datasetId?: string;
  };
  inference: {
    backend?: string;
    modelId?: string;
  };
  knowledge: {
    collectionId?: string;
  };
}

export interface RuntimeObservedState {
  backendStatus: 'connected' | 'disconnected' | 'checking';
  inference: {
    backends: RuntimeBackendInfo[];
    currentBackend: string;
    huggingfaceModels: RuntimeModelOption[];
    ollamaModels: RuntimeModelOption[];
    ollamaAvailable: boolean;
  };
  knowledge: {
    collections: RuntimeCollection[];
    embedderStatus: RuntimeEmbedderStatus | null;
  };
  training: RuntimeTrainingObserved;
}

export interface RuntimeDerivedState {
  activeBackend: string;
  activeModelId?: string;
  activeKnowledgeCollection: string;
  availableModelCount: number;
  runtimeStatus: 'ready' | 'degraded' | 'offline';
  warnings: string[];
  trainingSignal: RuntimeTrainingSignal;
}

export interface RuntimeContextValue {
  observed: RuntimeObservedState;
  selected: RuntimeSelectionState;
  derived: RuntimeDerivedState;
  actions: {
    refreshBootstrap: () => Promise<void>;
    refreshInference: () => Promise<void>;
    refreshKnowledge: () => Promise<void>;
    setTrainingSelection: (updates: Partial<RuntimeSelectionState['training']>) => void;
    setInferenceSelection: (updates: Partial<RuntimeSelectionState['inference']>) => void;
    setKnowledgeSelection: (updates: Partial<RuntimeSelectionState['knowledge']>) => void;
    syncInferenceSelection: (updates: Partial<RuntimeSelectionState['inference']>) => void;
    syncKnowledgeCollection: (collectionId?: string) => void;
  };
  backendStatus: 'connected' | 'disconnected' | 'checking';
  inference: {
    backends: RuntimeBackendInfo[];
    currentBackend: string;
    selectedBackend?: string;
    selectedModelId?: string;
    huggingfaceModels: RuntimeModelOption[];
    ollamaModels: RuntimeModelOption[];
    availableModelCount: number;
    ollamaAvailable: boolean;
    refresh: () => Promise<void>;
  };
  knowledge: {
    collections: RuntimeCollection[];
    selectedCollectionId: string;
    embedderStatus: RuntimeEmbedderStatus | null;
    refresh: () => Promise<void>;
  };
  chat: {
    backend: string;
    modelId: string;
    useKnowledge: boolean;
    knowledgeCollection?: string;
    useMemory: boolean;
    update: (updates: Partial<ReturnType<typeof useChatStore.getState>['settings']>) => void;
  };
  training: {
    modelId?: string;
    datasetId?: string;
  };
  summary: {
    activeBackend: string;
    activeModelId?: string;
    activeKnowledgeCollection: string;
    runtimeStatus: 'ready' | 'degraded' | 'offline';
    warnings: string[];
  };
  setTrainingSelection: (updates: Partial<RuntimeSelectionState['training']>) => void;
  setInferenceSelection: (updates: Partial<RuntimeSelectionState['inference']>) => void;
  setKnowledgeSelection: (updates: Partial<RuntimeSelectionState['knowledge']>) => void;
  syncInferenceSelection: (updates: Partial<RuntimeSelectionState['inference']>) => void;
  syncKnowledgeCollection: (collectionId?: string) => void;
}

const RuntimeContext = createContext<RuntimeContextValue | null>(null);

const TRAINING_PHASE_VALUES: RuntimeTrainingPhase[] = [
  'idle',
  'loading',
  'training',
  'running',
  'stopping',
  'stopped',
  'completed',
  'failed',
];

const normalizeTrainingPhase = (
  value: unknown,
  fallback: RuntimeTrainingPhase,
): RuntimeTrainingPhase => {
  if (typeof value !== 'string') return fallback;
  return (TRAINING_PHASE_VALUES as string[]).includes(value)
    ? (value as RuntimeTrainingPhase)
    : fallback;
};

const toTrainingSignal = (phase: RuntimeTrainingPhase): RuntimeTrainingSignal => {
  if (phase === 'completed') return { phase, label: '训练已完成', tone: 'success' };
  if (phase === 'failed') return { phase, label: '训练失败', tone: 'error' };
  if (phase === 'stopping') return { phase, label: '训练停止中', tone: 'warning' };
  if (phase === 'stopped') return { phase, label: '训练已停止', tone: 'warning' };
  if (phase === 'training' || phase === 'running')
    return { phase, label: '训练进行中', tone: 'info' };
  if (phase === 'loading') return { phase, label: '训练准备中', tone: 'info' };
  return { phase, label: '训练空闲', tone: 'info' };
};

export const RuntimeContextProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { backendStatus } = useAppStore();
  const chatSettings = useChatStore((state) => state.settings);
  const updateChatSettings = useChatStore((state) => state.updateSettings);

  const [selections, setSelections] = useState<RuntimeSelectionState>({
    training: {},
    inference: {},
    knowledge: {},
  });
  const [backends, setBackends] = useState<RuntimeBackendInfo[]>([]);
  const [currentBackend, setCurrentBackend] = useState('huggingface');
  const [huggingfaceModels, setHuggingfaceModels] = useState<RuntimeModelOption[]>([]);
  const [ollamaModels, setOllamaModels] = useState<RuntimeModelOption[]>([]);
  const [ollamaAvailable, setOllamaAvailable] = useState(false);
  const [collections, setCollections] = useState<RuntimeCollection[]>([]);
  const [embedderStatus, setEmbedderStatus] = useState<RuntimeEmbedderStatus | null>(null);
  const [trainingObserved, setTrainingObserved] = useState<RuntimeTrainingObserved>({
    isTraining: false,
    progressStatus: 'idle',
  });
  const [bootstrapWarnings, setBootstrapWarnings] = useState<string[]>([]);

  const applyBootstrapPayload = useCallback((payload: RuntimeBootstrapPayload) => {
    const inference = payload.observed.inference;
    const knowledge = payload.observed.knowledge;

    setBootstrapWarnings(payload.derived?.warnings || []);
    setCurrentBackend(inference.current_backend || 'huggingface');
    setBackends(
      (inference.backends || []).map((backend) => ({
        id: backend.id,
        name: backend.name,
        available: backend.available,
        description: backend.description,
      })),
    );
    setHuggingfaceModels(
      (inference.huggingface_models || []).map((model) => ({
        id: model.id,
        name: model.name || model.id,
      })),
    );
    setOllamaAvailable(Boolean(inference.ollama?.available || inference.ollama?.running));
    setOllamaModels(
      (inference.ollama?.models || []).map((model) => ({
        id: model.id || model.name,
        name: model.name || model.id,
      })),
    );
    setCollections(
      (knowledge.collections || []).map((collection) => ({
        id: collection.id,
        name: collection.name || collection.id,
        count: collection.count || 0,
      })),
    );
    setEmbedderStatus(knowledge.embedder_status || null);
    const rawTraining = payload.observed.training || {};
    const rawProgress = rawTraining.progress || null;
    const isTraining = Boolean(rawTraining.is_training);
    const progressStatus = normalizeTrainingPhase(
      rawProgress?.status,
      isTraining ? 'running' : 'idle',
    );
    const progressMessage =
      typeof rawProgress?.message === 'string' ? rawProgress.message : undefined;
    setTrainingObserved({
      isTraining,
      progressStatus,
      progressMessage,
    });
  }, []);

  const refreshInference = useCallback(async () => {
    if (backendStatus !== 'connected') return;

    try {
      const [backendData, hfModels] = await Promise.all([
        getBackends(),
        getInferenceModels().catch(() => []),
      ]);

      setCurrentBackend(backendData.current || 'huggingface');
      setBackends(
        (backendData.backends || []).map((backend: RuntimeBackendInfo) => ({
          id: backend.id,
          name: backend.name,
          available: backend.available,
          description: backend.description,
        })),
      );
      setHuggingfaceModels(
        (hfModels || []).map((model: { id: string; name?: string }) => ({
          id: model.id,
          name: model.name || model.id,
        })),
      );

      try {
        const ollamaStatus = await getOllamaStatus();
        setOllamaAvailable(Boolean(ollamaStatus?.available));
        setOllamaModels(
          (ollamaStatus?.models || []).map((model: { name: string }) => ({
            id: model.name,
            name: model.name,
          })),
        );
      } catch {
        setOllamaAvailable(false);
        setOllamaModels([]);
      }
    } catch (error) {
      console.error('Failed to refresh runtime inference context:', error);
    }
  }, [backendStatus]);

  const refreshKnowledge = useCallback(async () => {
    if (backendStatus !== 'connected') return;

    try {
      const [collectionsResponse, embedderResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/knowledge/collections`).catch(() => null),
        fetch(`${API_BASE_URL}/knowledge/embedder/status`).catch(() => null),
      ]);

      if (collectionsResponse?.ok) {
        const data = await collectionsResponse.json();
        setCollections(
          (data.collections || []).map((collection: { name: string; count?: number }) => ({
            id: collection.name,
            name: collection.name,
            count: collection.count || 0,
          })),
        );
      }

      if (embedderResponse?.ok) {
        const data = await embedderResponse.json();
        setEmbedderStatus(data);
      } else {
        setEmbedderStatus({ loaded: false, error: '无法连接到服务器' });
      }
    } catch (error) {
      console.error('Failed to refresh runtime knowledge context:', error);
      setEmbedderStatus({ loaded: false, error: '无法连接到服务器' });
    }
  }, [backendStatus]);

  const refreshBootstrap = useCallback(async () => {
    if (backendStatus !== 'connected') return;

    try {
      const payload = await getRuntimeBootstrap();
      applyBootstrapPayload(payload);
    } catch (error) {
      setBootstrapWarnings([]);
      const mode = (import.meta as unknown as { env?: { MODE?: string } }).env?.MODE;
      if (mode !== 'test') {
        console.warn('Runtime bootstrap failed, falling back to legacy runtime refresh:', error);
      }
      await Promise.all([refreshInference(), refreshKnowledge()]);
    }
  }, [applyBootstrapPayload, backendStatus, refreshInference, refreshKnowledge]);

  useEffect(() => {
    void refreshBootstrap();
  }, [refreshBootstrap]);

  useEffect(() => {
    if (backendStatus !== 'connected') {
      setBootstrapWarnings([]);
    }
  }, [backendStatus]);

  const setTrainingSelection = useCallback(
    (updates: Partial<RuntimeSelectionState['training']>) => {
      setSelections((prev) => ({
        ...prev,
        training: {
          ...prev.training,
          ...updates,
        },
      }));
    },
    [],
  );

  const setInferenceSelection = useCallback(
    (updates: Partial<RuntimeSelectionState['inference']>) => {
      setSelections((prev) => ({
        ...prev,
        inference: {
          ...prev.inference,
          ...updates,
        },
      }));
    },
    [],
  );

  const syncInferenceSelection = useCallback(
    (updates: Partial<RuntimeSelectionState['inference']>) => {
      setInferenceSelection(updates);

      const chatUpdates: Partial<ReturnType<typeof useChatStore.getState>['settings']> = {};
      if (updates.backend !== undefined) {
        chatUpdates.backend = updates.backend as 'ollama' | 'huggingface' | 'cloud';
      }
      if (updates.modelId !== undefined) {
        chatUpdates.modelId = updates.modelId;
      }

      if (Object.keys(chatUpdates).length > 0) {
        updateChatSettings(chatUpdates);
      }
    },
    [setInferenceSelection, updateChatSettings],
  );

  const setKnowledgeSelection = useCallback(
    (updates: Partial<RuntimeSelectionState['knowledge']>) => {
      setSelections((prev) => ({
        ...prev,
        knowledge: {
          ...prev.knowledge,
          ...updates,
        },
      }));
    },
    [],
  );

  const syncKnowledgeCollection = useCallback(
    (collectionId?: string) => {
      setKnowledgeSelection({ collectionId });
      updateChatSettings({ knowledgeCollection: collectionId });
    },
    [setKnowledgeSelection, updateChatSettings],
  );

  const value = useMemo<RuntimeContextValue>(() => {
    const activeBackend =
      selections.inference.backend || chatSettings.backend || currentBackend || 'huggingface';
    const activeModelId =
      selections.inference.modelId || chatSettings.modelId || selections.training.modelId;
    const activeKnowledgeCollection =
      selections.knowledge.collectionId || chatSettings.knowledgeCollection || 'default';
    const activeModelCount =
      activeBackend === 'ollama' ? ollamaModels.length : huggingfaceModels.length;
    const knowledgeEnabled = Boolean(
      chatSettings.useKnowledge || selections.knowledge.collectionId,
    );

    const warnings: string[] = [];
    warnings.push(...bootstrapWarnings);
    if (backendStatus !== 'connected') {
      warnings.push('后端当前未连接，运行上下文只保留本地选择态，无法代表真实服务状态。');
    }
    if (activeBackend === 'ollama' && !ollamaAvailable) {
      warnings.push('当前选择了 Ollama 后端，但运行时未检测到可用 Ollama 服务。');
    }
    if (knowledgeEnabled && !embedderStatus?.loaded) {
      warnings.push('知识库嵌入模型尚未就绪，检索和上传后的向量化能力会受限。');
    }
    if (trainingObserved.progressStatus === 'failed') {
      warnings.push(
        trainingObserved.progressMessage
          ? `训练运行态异常：${trainingObserved.progressMessage}`
          : '训练运行态异常：最近一次训练失败，请先排查后再继续关键链路操作。',
      );
    }
    if (trainingObserved.progressStatus === 'stopping') {
      warnings.push('训练任务正在停止中，建议等待状态收敛后再执行新的训练/推理切换操作。');
    }

    const observed: RuntimeObservedState = {
      backendStatus,
      inference: {
        backends,
        currentBackend,
        huggingfaceModels,
        ollamaModels,
        ollamaAvailable,
      },
      knowledge: {
        collections,
        embedderStatus,
      },
      training: trainingObserved,
    };

    const derived: RuntimeDerivedState = {
      activeBackend,
      activeModelId,
      activeKnowledgeCollection,
      availableModelCount: activeModelCount,
      runtimeStatus:
        backendStatus !== 'connected' ? 'offline' : warnings.length > 0 ? 'degraded' : 'ready',
      warnings,
      trainingSignal: toTrainingSignal(trainingObserved.progressStatus),
    };

    const actions = {
      refreshBootstrap,
      refreshInference,
      refreshKnowledge,
      setTrainingSelection,
      setInferenceSelection,
      setKnowledgeSelection,
      syncInferenceSelection,
      syncKnowledgeCollection,
    };

    return {
      observed,
      selected: selections,
      derived,
      actions,
      backendStatus,
      inference: {
        backends,
        currentBackend,
        selectedBackend: selections.inference.backend,
        selectedModelId: selections.inference.modelId,
        huggingfaceModels,
        ollamaModels,
        availableModelCount: activeModelCount,
        ollamaAvailable,
        refresh: refreshInference,
      },
      knowledge: {
        collections,
        selectedCollectionId: activeKnowledgeCollection,
        embedderStatus,
        refresh: refreshKnowledge,
      },
      chat: {
        backend: chatSettings.backend,
        modelId: chatSettings.modelId,
        useKnowledge: chatSettings.useKnowledge,
        knowledgeCollection: chatSettings.knowledgeCollection,
        useMemory: chatSettings.useMemory,
        update: updateChatSettings,
      },
      training: selections.training,
      summary: {
        activeBackend: derived.activeBackend,
        activeModelId: derived.activeModelId,
        activeKnowledgeCollection: derived.activeKnowledgeCollection,
        runtimeStatus: derived.runtimeStatus,
        warnings: derived.warnings,
      },
      setTrainingSelection,
      setInferenceSelection,
      setKnowledgeSelection,
      syncInferenceSelection,
      syncKnowledgeCollection,
    };
  }, [
    backendStatus,
    backends,
    bootstrapWarnings,
    chatSettings,
    collections,
    currentBackend,
    embedderStatus,
    huggingfaceModels,
    ollamaAvailable,
    ollamaModels,
    refreshInference,
    refreshBootstrap,
    refreshKnowledge,
    selections.inference,
    selections.knowledge,
    selections.training,
    setInferenceSelection,
    setKnowledgeSelection,
    setTrainingSelection,
    syncInferenceSelection,
    syncKnowledgeCollection,
    trainingObserved,
    updateChatSettings,
  ]);

  return <RuntimeContext.Provider value={value}>{children}</RuntimeContext.Provider>;
};

export const useRuntimeContext = () => {
  const context = useContext(RuntimeContext);
  if (!context) {
    throw new Error('useRuntimeContext must be used within RuntimeContextProvider');
  }
  return context;
};
