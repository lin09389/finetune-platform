import { Button, Collapse, Drawer, Modal, Tag } from 'antd';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';

import { useChatStream } from '../hooks/chat/useChatStream';
import { useResponsive } from '../hooks/useResponsive';
import { useShallow } from 'zustand/react/shallow';
import { useChatStore } from '../store/chatStore';
import { useTheme } from '../theme';
import { appModal } from '../utils/modal';

import ChatHeader from '../components/chat/ChatHeader';
import ChatContextPanel from '../components/chat/ChatContextPanel';
import ChatInput from '../components/chat/ChatInput';
import AgentPhaseIndicator from '../components/chat/AgentPhaseIndicator';
import AgentWorkbenchPanel, { WorkbenchEmpty } from '../components/chat/AgentWorkbenchPanel';
import ChatHistoryDrawer from '../components/ChatHistoryDrawer';
import ChatMessage from '../components/ChatMessage';
import MemoryManager from '../components/MemoryManager';
import APIKeyManager from '../pages/APIKeyManager';

import { useRuntimeContext } from '../runtime/RuntimeContext';
import {
  API_BASE_URL,
  approveAgentAction,
  classifyChatAgentIntent,
  createAgentSession,
  executeAgentAction,
  getAgentSession,
  getAgentSessionOverview,
  getPrimaryAgents,
  getSavedCloudProviderData,
  getSavedCloudProviders,
  interruptAgentSession,
  listWorkspaces,
  promptAgentSession,
  rejectAgentAction as rejectAgentSessionAction,
} from '../services/api';
import type { AgentArtifact, AgentInfo, AgentPart, AgentSession, AgentSessionEvent, AgentSessionOverview, SavedCloudProvider, WorkspaceSummary } from '../services/api';
import { transitions } from '../theme/animations';
import { notify } from '../utils/notify';
import { ArrowDownOutlined } from '@ant-design/icons';
import styles from './ChatNew.module.css';

interface APIKeyConfig {
  provider: string;
  api_key?: string;
  key_id?: string;
  model?: string;
  group_id?: string;
  base_url?: string;
}

const STARTER_IDEAS = [
  {
    title: '学习与规划',
    desc: '帮我制定一个深度学习入门计划',
    icon: '📚'
  },
  {
    title: '模型微调',
    desc: '如何进行大模型 QLoRA 微调？',
    icon: '⚡'
  },
  {
    title: '代码助理',
    desc: '用 Python 写一个分布式爬虫示例',
    icon: '💻'
  },
  {
    title: '数据分析',
    desc: '分析当前大语言模型的技术趋势',
    icon: '📊'
  }
];

const sectionMotion = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.26, ease: [0.16, 1, 0.3, 1] as const },
};

interface StoredChatScrollState {
  topIndex: number;
  atBottom: boolean;
  updatedAt: string;
}

const CHAT_SCROLL_STORAGE_KEY = 'chat_scroll_positions_v1';
const INTENT_ROUTING_TIMEOUT_MS = 8000;
const CHAT_WORKSPACE_ID_STORAGE_KEY = 'chat_workspace_id_v1';
const CHAT_PROJECT_PATH_STORAGE_KEY = 'chat_project_path_v1';
const CHAT_WORKSPACE_EVENT = 'chat-workspace-change';
const CHAT_SIDE_PANEL_WIDTH_STORAGE_KEY = 'chat_side_panel_width_v1';

const withTimeout = async <T,>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> => {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
};

const clampMessageIndex = (index: number, messageCount: number) => {
  if (messageCount <= 0) return 0;
  return Math.min(Math.max(index, 0), messageCount - 1);
};

const readStoredScrollMap = (): Record<string, StoredChatScrollState> => {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(CHAT_SCROLL_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object'
      ? (parsed as Record<string, StoredChatScrollState>)
      : {};
  } catch {
    return {};
  }
};

const getStoredScrollState = (sessionId: string | null): StoredChatScrollState | null => {
  if (!sessionId) return null;
  return readStoredScrollMap()[sessionId] || null;
};

const persistScrollState = (
  sessionId: string | null,
  scrollState: StoredChatScrollState,
) => {
  if (typeof window === 'undefined' || !sessionId) return;
  const next = {
    ...readStoredScrollMap(),
    [sessionId]: scrollState,
  };
  localStorage.setItem(CHAT_SCROLL_STORAGE_KEY, JSON.stringify(next));
};


const ChatPage: React.FC = () => {
  useTheme();
  const { isMobile, isDesktop } = useResponsive();
  const prefersReducedMotion = useReducedMotion();
  const runtime = useRuntimeContext();
  const { actions, derived, observed } = runtime;
  const {
    refreshInference,
    refreshKnowledge,
    setInferenceSelection,
    setKnowledgeSelection,
    syncKnowledgeCollection,
  } = actions;

  const enableVirtualScroll = false;

  const {
    sessions,
    currentSessionId,
    messages,
    settings,
    isLoading,
    addMessage,
    createSession,
    loadSession,
    deleteSession,
    loadSessions,
    deleteMessage,
    removeLocalMessage,
    clearMessages,
    replaceCurrentSessionMessages,
    updateSettings,
  } = useChatStore(useShallow((state) => ({
    sessions: state.sessions,
    currentSessionId: state.currentSessionId,
    messages: state.messages,
    settings: state.settings,
    isLoading: state.isLoading,
    addMessage: state.addMessage,
    createSession: state.createSession,
    loadSession: state.loadSession,
    deleteSession: state.deleteSession,
    loadSessions: state.loadSessions,
    deleteMessage: state.deleteMessage,
    removeLocalMessage: state.removeLocalMessage,
    clearMessages: state.clearMessages,
    replaceCurrentSessionMessages: state.replaceCurrentSessionMessages,
    updateSettings: state.updateSettings,
  })));

  const [historyOpen, setHistoryOpen] = useState(false);
  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false);
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [contextPanelOpen, setContextPanelOpen] = useState(false);

  const { cloudConfig, setCloudConfig } = useChatStore(useShallow((state) => ({
    cloudConfig: state.cloudConfig,
    setCloudConfig: state.setCloudConfig,
  })));
  const useCloudAI = cloudConfig.useCloudAI;
  const setUseCloudAI = (val: boolean | ((prev: boolean) => boolean)) => {
    const next = typeof val === 'function' ? val(cloudConfig.useCloudAI) : val;
    setCloudConfig({ useCloudAI: next });
  };
  const cloudAIConfig = cloudConfig.config as APIKeyConfig | null;
  const setCloudAIConfig = (cfg: APIKeyConfig | null) => setCloudConfig({ config: cfg });
  const cloudProviders = cloudConfig.providers as SavedCloudProvider[];
  const setCloudProviders = (providers: SavedCloudProvider[]) => setCloudConfig({ providers: providers as any });
  const selectedCloudModel = cloudConfig.selectedModel;
  const setSelectedCloudModel = (model: string) => setCloudConfig({ selectedModel: model });
  const [primaryAgents, setPrimaryAgents] = useState<AgentInfo[]>([]);
  const [selectedPrimaryAgent, setSelectedPrimaryAgent] = useState('build');
  const [routingMode, setRoutingMode] = useState<'auto' | 'chat' | 'agent'>(
    () => {
      const saved = localStorage.getItem('chat_routing_mode');
      return saved === 'chat' || saved === 'agent' || saved === 'auto' ? saved : 'auto';
    },
  );
  const [autonomyMode, setAutonomyMode] = useState<'safe_auto' | 'confirm_all' | 'read_only'>(
    () => {
      const saved = localStorage.getItem('chat_agent_autonomy_mode');
      return saved === 'confirm_all' || saved === 'read_only' || saved === 'safe_auto' ? saved : 'safe_auto';
    },
  );
  const [routingIntent, setRoutingIntent] = useState(false);
  const [creatingAgentSession, setCreatingAgentSession] = useState(false);
  const [availableWorkspaces, setAvailableWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>(() => localStorage.getItem(CHAT_WORKSPACE_ID_STORAGE_KEY) || '');
  const [workspaceProjectPath, setWorkspaceProjectPath] = useState<string>(() => localStorage.getItem(CHAT_PROJECT_PATH_STORAGE_KEY) || '');
  const [workspaceTreeFocusedOnly, setWorkspaceTreeFocusedOnly] = useState(false);
  const [agentSessionOverview, setAgentSessionOverview] = useState<AgentSessionOverview | null>(null);
  const agentSessionStreamsRef = useRef<Record<string, EventSource>>({});
  const agentSessionStateRef = useRef<Record<string, AgentSession>>({});
  const refreshedAgentSessionsRef = useRef<Set<string>>(new Set());
  const streamingDeltaRef = useRef<Record<string, { partId: string; content: string }>>({});
  const agentDeltaFlushRef = useRef<{ rafId: number | null; pending: Record<string, string> } | null>(null);
  const [agentPhase, setAgentPhase] = useState<{ phase: string; tool?: string; detail?: string; visible: boolean }>({ phase: '', visible: false });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle | null>(null);
  const visibleRangeStartRef = useRef(0);
  const isAutoScrollEnabledRef = useRef(true);
  const restoredSessionRef = useRef<string | null>(null);
  const savedScrollState = useMemo(
    () => getStoredScrollState(currentSessionId),
    [currentSessionId],
  );
  const shouldRestoreToBottom = savedScrollState?.atBottom !== false;
  const initialTopMostItemIndex = useMemo(() => {
    if (messages.length === 0) return undefined;
    if (shouldRestoreToBottom) return messages.length - 1;
    return clampMessageIndex(savedScrollState?.topIndex ?? messages.length - 1, messages.length);
  }, [messages.length, savedScrollState?.topIndex, shouldRestoreToBottom]);
  const [, setIsAtBottom] = useState(shouldRestoreToBottom);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [sidePanelWidth, setSidePanelWidth] = useState(() => {
    if (typeof window === 'undefined') return 360;
    const stored = Number(localStorage.getItem(CHAT_SIDE_PANEL_WIDTH_STORAGE_KEY));
    return Number.isFinite(stored) && stored >= 280 ? stored : 360;
  });
  const [resizingSidePanel, setResizingSidePanel] = useState(false);
  const autoScrollFrameRef = useRef<number | null>(null);
  const pendingAutoScrollRef = useRef(false);

  const saveCurrentScrollState = useCallback(
    (overrides?: Partial<StoredChatScrollState>) => {
      if (!currentSessionId || currentSessionId.startsWith('local_')) return;
      if (messages.length === 0) return;
      persistScrollState(currentSessionId, {
        topIndex: clampMessageIndex(visibleRangeStartRef.current, messages.length),
        atBottom: isAutoScrollEnabledRef.current,
        updatedAt: new Date().toISOString(),
        ...overrides,
      });
    },
    [currentSessionId, messages.length],
  );

  const selectedWorkspace = useMemo(
    () => availableWorkspaces.find((workspace) => workspace.id === selectedWorkspaceId) || null,
    [availableWorkspaces, selectedWorkspaceId],
  );
  const selectedWorkspaceLabel = selectedWorkspace
    ? `${selectedWorkspace.name}${selectedWorkspace.local_path ? ` · ${selectedWorkspace.local_path}` : ''}`
    : '未选择工作区';
  const effectiveProjectPath = (workspaceProjectPath.trim() || selectedWorkspace?.local_path || '').trim();
  useEffect(() => {
    setIsAtBottom(shouldRestoreToBottom);
    isAutoScrollEnabledRef.current = shouldRestoreToBottom;
    setShowScrollButton(messages.length > 0 && !shouldRestoreToBottom);
  }, [currentSessionId, messages.length, shouldRestoreToBottom]);

  useEffect(() => () => {
    saveCurrentScrollState();
  }, [saveCurrentScrollState]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const resizingClassName = styles.resizing;
    if (!resizingClassName) return;
    document.body.classList.toggle(resizingClassName, resizingSidePanel);
    return () => document.body.classList.remove(resizingClassName);
  }, [resizingSidePanel]);

  const handleSplitterPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidePanelWidth;
    const minSideWidth = 280;
    const maxSideWidth = Math.max(320, window.innerWidth - 520);
    setResizingSidePanel(true);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const nextWidth = Math.min(
        maxSideWidth,
        Math.max(minSideWidth, startWidth - (moveEvent.clientX - startX)),
      );
      setSidePanelWidth(nextWidth);
    };

    const handlePointerUp = () => {
      setResizingSidePanel(false);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  }, [sidePanelWidth]);

  useEffect(() => {
    localStorage.setItem(CHAT_SIDE_PANEL_WIDTH_STORAGE_KEY, String(sidePanelWidth));
  }, [sidePanelWidth]);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const { scrollTop, scrollHeight, clientHeight } = target;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 150;
    isAutoScrollEnabledRef.current = isAtBottom;
    setShowScrollButton(!isAtBottom);
  }, []);

  const scrollToBottom = useCallback((smooth: boolean = true, force: boolean = false) => {
    if (!force && !isAutoScrollEnabledRef.current) return;
    if (messages.length === 0) return;
    
    if (autoScrollFrameRef.current !== null) {
      cancelAnimationFrame(autoScrollFrameRef.current);
      autoScrollFrameRef.current = null;
    }

    autoScrollFrameRef.current = requestAnimationFrame(() => {
      autoScrollFrameRef.current = null;
      if (!force && !isAutoScrollEnabledRef.current) return;

      if (virtuosoRef.current && enableVirtualScroll) {
        virtuosoRef.current.scrollToIndex({
          index: messages.length - 1,
          align: 'end',
          behavior: smooth ? 'smooth' : 'auto',
        });
        return;
      }

      if (scrollContainerRef.current) {
        const { scrollHeight, clientHeight } = scrollContainerRef.current;
        scrollContainerRef.current.scrollTo({
          top: Math.max(0, scrollHeight - clientHeight),
          behavior: smooth ? 'smooth' : 'auto',
        });
      }
    });
  }, [messages.length, enableVirtualScroll]);

  const {
    sendMessage,
    sendCloudMessage,
    stop: stopStream,
    isStreaming: isActivelyStreaming,
  } = useChatStream({
    onChunk: () => {
      // streaming chunk hook
    },
    onComplete: () => {
      // stream completed
    },
    onError: (error) => {
      notify.error(error);
    },
  });

  const activeAgentSessionIds = useMemo(() => {
    const activeStatuses = new Set(['running', 'verifying', 'repairing', 'waiting_approval', 'waiting_permission']);
    return Array.from(
      new Set(
        messages
          .filter((message) => {
            const metadata = message.agent_metadata;
            return Boolean(
              metadata?.agent_session_id &&
              (activeStatuses.has(metadata.status || '') || message.isLoading),
            );
          })
          .map((message) => message.agent_metadata?.agent_session_id)
          .filter((sessionId): sessionId is string => Boolean(sessionId)),
      ),
    );
  }, [messages]);

  const isAgentSessionRunning = activeAgentSessionIds.length > 0;

  // Keep the viewport pinned to the bottom while streaming when auto-scroll is enabled.
  useEffect(() => {
    if (enableVirtualScroll || !isAutoScrollEnabledRef.current) return;
    pendingAutoScrollRef.current = true;
    if (autoScrollFrameRef.current !== null) return;

    autoScrollFrameRef.current = requestAnimationFrame(() => {
      autoScrollFrameRef.current = null;
      if (!pendingAutoScrollRef.current || !isAutoScrollEnabledRef.current) return;
      pendingAutoScrollRef.current = false;
      scrollToBottom(false, true);
    });
  }, [enableVirtualScroll, isActivelyStreaming, messages.length, scrollToBottom]);

  // Use ResizeObserver for robust auto-scroll during content updates
  useEffect(() => {
    if (enableVirtualScroll || !scrollContainerRef.current) return;

    const container = scrollContainerRef.current;
    let lastHeight = container.scrollHeight;
    let lastScrollTop = container.scrollTop;
    let rafId: number | null = null;

    const resizeObserver = new ResizeObserver(() => {
      const newHeight = container.scrollHeight;
      const newScrollTop = container.scrollTop;
      if (newHeight === lastHeight && newScrollTop === lastScrollTop) return;

      lastHeight = newHeight;
      lastScrollTop = newScrollTop;

      if (!isAutoScrollEnabledRef.current) return;

      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        rafId = null;
        const nextTop = Math.max(0, container.scrollHeight - container.clientHeight);
        if (Math.abs(container.scrollTop - nextTop) > 1) {
          container.scrollTop = nextTop;
        }
      });
    });

    resizeObserver.observe(container);
    return () => {
      resizeObserver.disconnect();
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [enableVirtualScroll]);

  useEffect(() => {
    Promise.allSettled([
      refreshInference(),
      loadSessions(),
      loadCloudAIConfig(),
      loadPrimaryAgents(),
      refreshKnowledge(),
    ]).then((results) => {
      const failed = results.filter((r) => r.status === 'rejected');
      if (failed.length > 0) {
        console.warn(`${failed.length} init requests failed`);
      }
    });
  }, [loadSessions, refreshInference, refreshKnowledge]);

  useEffect(() => () => {
    if (autoScrollFrameRef.current !== null) cancelAnimationFrame(autoScrollFrameRef.current);
    Object.values(agentSessionStreamsRef.current).forEach((source) => source.close());
  }, []);

  useEffect(() => {
    localStorage.setItem('chat_primary_agent', selectedPrimaryAgent);
  }, [selectedPrimaryAgent]);

  useEffect(() => {
    localStorage.setItem('chat_routing_mode', routingMode);
  }, [routingMode]);

  useEffect(() => {
    localStorage.setItem('chat_agent_autonomy_mode', autonomyMode);
  }, [autonomyMode]);

  useEffect(() => {
    localStorage.setItem(CHAT_WORKSPACE_ID_STORAGE_KEY, selectedWorkspaceId);
  }, [selectedWorkspaceId]);

  useEffect(() => {
    localStorage.setItem(CHAT_PROJECT_PATH_STORAGE_KEY, workspaceProjectPath);
  }, [workspaceProjectPath]);

  useEffect(() => {
    const handleWorkspaceChange = (event: Event) => {
      const detail = (event as CustomEvent<{ workspaceId?: string; projectPath?: string }>).detail || {};
      setSelectedWorkspaceId(detail.workspaceId || '');
      setWorkspaceProjectPath(detail.projectPath || '');
    };
    window.addEventListener(CHAT_WORKSPACE_EVENT, handleWorkspaceChange);
    return () => window.removeEventListener(CHAT_WORKSPACE_EVENT, handleWorkspaceChange);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadWorkspaceOptions = async () => {
      try {
        const workspaces = await listWorkspaces();
        if (cancelled) return;
        setAvailableWorkspaces(workspaces);
        const selected =
          workspaces.find((workspace) => workspace.id === selectedWorkspaceId) ||
          workspaces.find((workspace) => workspace.status === 'default' && workspace.local_path) ||
          workspaces.find((workspace) => workspace.local_path);
        if (!selectedWorkspaceId && selected?.id) {
          setSelectedWorkspaceId(selected.id);
        }
        if (selected?.local_path && !workspaceProjectPath.trim()) {
          setWorkspaceProjectPath(selected.local_path);
        }
      } catch {
        if (!cancelled) setAvailableWorkspaces([]);
      }
    };
    void loadWorkspaceOptions();
    return () => {
      cancelled = true;
    };
  }, [selectedWorkspaceId, workspaceProjectPath]);

  useEffect(() => {
    if (!currentSessionId || currentSessionId.startsWith('local_')) return;
    if (messages.length > 0) {
      restoredSessionRef.current = currentSessionId;
      return;
    }
    if (restoredSessionRef.current === currentSessionId) return;
    restoredSessionRef.current = currentSessionId;
    loadSession(currentSessionId).catch((error) => {
      const message = error instanceof Error ? error.message : '历史会话恢复失败';
      notify.error(`历史会话恢复失败：${message}`);
    });
  }, [currentSessionId, loadSession, messages.length]);

  useEffect(() => {
    localStorage.setItem('chat_use_cloud_ai', useCloudAI ? '1' : '0');
  }, [useCloudAI]);

  useEffect(() => {
    if (settings.knowledgeCollection) {
      setKnowledgeSelection({ collectionId: settings.knowledgeCollection });
    }
  }, [setKnowledgeSelection, settings.knowledgeCollection]);

  useEffect(() => {
    setInferenceSelection({
      backend: settings.backend,
      modelId: settings.modelId || undefined,
    });
  }, [setInferenceSelection, settings.backend, settings.modelId]);

  // Virtuoso's followOutput handles auto-scrolling to bottom.
  // We don't manually call scrollToBottom on messages change to prevent forcing users to the bottom when they scroll up.

  const loadCloudAIConfig = async (force = false) => {
    // If already loaded from store cache, skip re-fetching unless forced
    if (!force && cloudConfig.providers.length > 0) {
      // Apply use cloud AI preference from localStorage if needed
      if (cloudConfig.config?.key_id || cloudConfig.config?.api_key) {
        setUseCloudAI(localStorage.getItem('chat_use_cloud_ai') === '1');
      }
      return;
    }
    try {
      const data = await getSavedCloudProviders();
      const keys: SavedCloudProvider[] = data.keys || [];
      setCloudProviders(keys);

      if (keys.length > 0) {
        const saved = localStorage.getItem('cloud_ai_config');
        let preferredProvider = '';
        let preferredModel = '';
        if (saved) {
          try {
            const savedConfig = JSON.parse(saved);
            preferredProvider = savedConfig.provider || '';
            preferredModel = savedConfig.model || '';
          } catch {
            preferredProvider = '';
          }
        }

        const firstKey = keys.find((key) => key.provider === preferredProvider) || keys[0];
        if (firstKey) {
          const keyData = await getSavedCloudProviderData(firstKey.id).catch(() => ({}));
          const models = keyData.models || firstKey.models || [];
          const selectedModel =
            preferredModel ||
            keyData.default_model ||
            firstKey.default_model ||
            models[0] ||
            '';

          const config: APIKeyConfig = {
            provider: firstKey.provider,
            api_key: '',
            key_id: firstKey.id,
            model: selectedModel,
            group_id: keyData.group_id || '',
            base_url: keyData.base_url || '',
          };
          setCloudAIConfig(config);
          setUseCloudAI(localStorage.getItem('chat_use_cloud_ai') === '1');
          setSelectedCloudModel(selectedModel);
          localStorage.setItem('cloud_ai_config', JSON.stringify(config));
          return;
        }
      }
    } catch {
      console.log('Failed to load cloud config from backend');
    }

    const saved = localStorage.getItem('cloud_ai_config');
    if (saved) {
      try {
        const config = JSON.parse(saved);
        setCloudAIConfig(config);
        setUseCloudAI(localStorage.getItem('chat_use_cloud_ai') === '1');
        if (config.model) {
          setSelectedCloudModel(config.model);
        }
      } catch (e) {
        console.error('Failed to parse cloud config:', e);
      }
    }
  };

  const loadPrimaryAgents = async () => {
    try {
      const agents = await getPrimaryAgents();
      setPrimaryAgents(agents || []);
      const saved = localStorage.getItem('chat_primary_agent') || 'build';
      if (agents?.some((a: AgentInfo) => a.id === saved)) {
        setSelectedPrimaryAgent(saved);
      } else if (agents?.[0]?.id) {
        setSelectedPrimaryAgent(agents[0].id);
      }
    } catch {
      setPrimaryAgents([]);
    }
  };

  const isLikelyAgentGoal = useCallback((content: string) => {
    const text = content.trim().toLowerCase();
    if (!text) return false;
    if (['不要执行', '只讨论', '只分析', '解释一下', '帮我解释', '什么是', '为什么',
      '怎么理解', '怎么用', '是什么意思', '有什么区别', '介绍一下', '帮我看看',
      '分析一下', '看看代码', '这个代码', '这段代码', '看看逻辑', '怎么实现的',
      '原理是什么', '怎么工作的', '帮我梳理', '帮我看看代码'].some((keyword) => text.includes(keyword))) {
      return false;
    }
    return [
      '修改代码',
      '新增功能',
      '新增接口',
      '新增页面',
      '实现功能',
      '实现接口',
      '修复bug',
      '修复报错',
      '重构代码',
      '优化代码',
      '跑测试',
      '运行测试',
      'typecheck',
      'pytest',
      'npm run',
      '让agent做',
      '自动处理',
      '生成补丁',
      '写补丁',
      '搜索项目',
      '写脚本',
      '排查报错',
      '排查问题',
      '运行命令',
      '执行补丁',
      '帮我改',
      '帮我修',
      '帮我写',
      '帮我实现',
      '帮我新增',
      '帮我添加',
      '帮我重构',
      '改成',
      '改为',
      '加个',
      '加一个',
      '删掉',
      '删除',
      '创建',
      '新建',
      '安装',
      '配置',
      '部署',
      '写个',
      '写一个',
      '运行',
      '执行',
      '启动',
      '打包',
      '上传',
      '更新',
      '重命名',
    ].some((keyword) => text.includes(keyword));
  }, []);

  const persistAgentMessages = useCallback(async () => {
    const state = useChatStore.getState();
    if (!state.currentSessionId || state.currentSessionId.startsWith('local_')) return;
    await state.replaceCurrentSessionMessages(state.messages).catch(() => undefined);
  }, []);

  const rememberAgentSession = useCallback((session: AgentSession) => {
    agentSessionStateRef.current[session.id] = session;
    return session;
  }, []);

  const ensureAgentSessionSnapshot = useCallback((
    sessionId: string,
    overrides: Partial<AgentSession> = {},
  ): AgentSession => {
    const cached = agentSessionStateRef.current[sessionId];
    const next: AgentSession = {
      id: sessionId,
      chat_session_id: overrides.chat_session_id ?? cached?.chat_session_id,
      agent_id: overrides.agent_id ?? cached?.agent_id ?? 'build',
      status: overrides.status ?? cached?.status ?? 'running',
      title: overrides.title ?? cached?.title ?? 'Agent Session',
      project_path: overrides.project_path ?? cached?.project_path,
      provider: overrides.provider ?? cached?.provider,
      model: overrides.model ?? cached?.model,
      metadata: overrides.metadata ?? cached?.metadata ?? {},
      parts: overrides.parts ?? cached?.parts ?? [],
      created_at: overrides.created_at ?? cached?.created_at ?? new Date().toISOString(),
      updated_at: overrides.updated_at ?? cached?.updated_at ?? new Date().toISOString(),
    };
    agentSessionStateRef.current[sessionId] = next;
    return next;
  }, []);

  const mergeAgentSessionPart = useCallback((
    sessionId: string,
    part: AgentPart,
    overrides: Partial<AgentSession> = {},
  ): AgentSession => {
    const session = ensureAgentSessionSnapshot(sessionId, overrides);
    const parts = [...(session.parts || [])];
    const index = parts.findIndex((item) => item.id === part.id);
    if (index >= 0) {
      parts[index] = { ...parts[index], ...part };
    } else {
      parts.push(part);
    }
    const next = {
      ...session,
      ...overrides,
      parts,
      updated_at: part.updated_at || overrides.updated_at || session.updated_at,
    };
    agentSessionStateRef.current[sessionId] = next;
    return next;
  }, [ensureAgentSessionSnapshot]);

  const buildAgentPartMetadata = useCallback((session: AgentSession, part: any) => {
    const actionLike = ['diff', 'permission', 'command'].includes(part.type);
    const summaryPart = part.type === 'summary' ? part : [...(session.parts || [])].reverse().find((item) => item.type === 'summary');
    return {
      agent_run_id: session.id,
      agent_session_id: session.id,
      agent_part_id: part.id,
      kind: 'agent_part' as const,
      status: part.status || session.status,
      action_id: actionLike ? part.id : undefined,
      action_type: part.type === 'diff' ? 'patch' : part.type,
      can_approve: actionLike && part.status === 'pending',
      can_execute: ['diff', 'command'].includes(part.type) && part.status === 'approved',
      active_agent_id: session.agent_id,
      task_plan: session.metadata?.task_plan,
      current_stage_id: session.metadata?.current_stage_id,
      current_node_id: session.metadata?.current_node_id,
      agent_part: part,
      agent_session_state: (session.metadata as any)?.state,
      agent_session_diagnostics: (session.metadata as any)?.diagnostics,
      agent_streaming_diagnostics: (session.metadata as any)?.streaming_diagnostics,
      final_summary: summaryPart?.content,
      recoverable: !['completed', 'failed'].includes(session.status),
      autonomy_mode: (session.metadata as any)?.autonomy_mode,
    };
  }, []);

  const upsertAgentSessionMessage = useCallback(
    async (session: AgentSession, fallbackContent?: string) => {
      rememberAgentSession(session);
      const state = useChatStore.getState();
      const renderableParts = (session.parts || []).filter((part) => !(part.type === 'text' && part.title === '请求'));
      if (!renderableParts.length && fallbackContent) {
        const placeholderId = `${session.id}:pending`;
        const existing = state.messages.find((message) => message.agent_metadata?.agent_part_id === placeholderId);
        const placeholderPart = {
          id: placeholderId,
          session_id: session.id,
          type: 'text',
          status: session.status === 'running' ? 'running' : 'completed',
          title: 'Agent 已启动',
          content: fallbackContent,
          payload: {},
          created_at: session.updated_at,
        };
        const metadata = buildAgentPartMetadata(session, placeholderPart);
        if (existing) {
          state.updateMessage(existing.id, { content: fallbackContent, isLoading: session.status === 'running', agent_metadata: metadata });
        } else {
          state.addMessage({ role: 'assistant', content: fallbackContent, isLoading: session.status === 'running', agent_metadata: metadata });
        }
        await persistAgentMessages();
        return;
      }

      for (const part of renderableParts) {
        const existing = state.messages.find((message) => message.agent_metadata?.agent_part_id === part.id);
        const content = part.content || part.title || session.title;
        const metadata = buildAgentPartMetadata(session, part);
if (existing) {
          state.queueMessageUpdate(existing.id, {
            content,
            isLoading: part.status === 'running',
            agent_metadata: metadata,
          });
        } else {
          state.addMessage({
            role: 'assistant',
            content,
            isLoading: part.status === 'running',
            agent_metadata: metadata,
          });
        }
      }

      const placeholder = state.messages.find((message) => message.agent_metadata?.agent_part_id === `${session.id}:pending`);
      if (placeholder && renderableParts.length) {
        await state.deleteMessage(placeholder.id).catch(() => undefined);
      }
      state.flushMessageUpdates();
      await persistAgentMessages();
    },
    [buildAgentPartMetadata, persistAgentMessages, rememberAgentSession],
  );

  const upsertAgentSessionPartMessage = useCallback(
    async (
      sessionId: string,
      part: AgentPart,
      overrides: Partial<AgentSession> = {},
      options: { persist?: boolean } = {},
    ) => {
      if (part.type === 'text' && part.title === '请求') return;
      const state = useChatStore.getState();
      const session = mergeAgentSessionPart(sessionId, part, overrides);
      const content = part.content || part.title || session.title;
      const metadata = buildAgentPartMetadata(session, part);
      const existing = state.messages.find((message) => message.agent_metadata?.agent_part_id === part.id);
      if (existing) {
        state.queueMessageUpdate(existing.id, {
          content,
          isLoading: part.status === 'running',
          agent_metadata: metadata,
        });
      } else {
        state.addMessage({
          role: 'assistant',
          content,
          isLoading: part.status === 'running',
          agent_metadata: metadata,
        });
      }
      const placeholder = state.messages.find((message) => message.agent_metadata?.agent_part_id === `${sessionId}:pending`);
      if (placeholder) {
        await state.deleteMessage(placeholder.id).catch(() => undefined);
      }
      state.flushMessageUpdates();
      if (options.persist) {
        await persistAgentMessages();
      }
    },
    [buildAgentPartMetadata, mergeAgentSessionPart, persistAgentMessages],
  );

  const appendAgentSessionError = useCallback(
    async (content: string, session?: Partial<AgentSession> & { id?: string }) => {
      const now = new Date().toISOString();
      const sessionId = session?.id || `agent_error_${Date.now()}`;
      const errorPart: AgentPart = {
        id: `${sessionId}:startup-error`,
        session_id: sessionId,
        type: 'error',
        status: 'failed',
        title: 'Agent 启动失败',
        content,
        payload: {
          guidance: '已停止本次 Agent 执行，没有重复调用工具。可以检查后端日志或稍后重试。',
          fallback: true,
        },
        created_at: now,
        updated_at: now,
      };
      const snapshot = ensureAgentSessionSnapshot(sessionId, {
        ...session,
        id: sessionId,
        status: 'failed',
        title: session?.title || 'Agent Session',
        metadata: {
          ...(session?.metadata || {}),
          diagnostics: {
            stop_reason: content,
            next_action: '检查后端服务状态、模型配置或权限后再重试。',
            refresh_safe: true,
          },
        },
        parts: [errorPart],
        updated_at: now,
      } as Partial<AgentSession>);
      await upsertAgentSessionPartMessage(sessionId, errorPart, snapshot, { persist: true });
    },
    [ensureAgentSessionSnapshot, upsertAgentSessionPartMessage],
  );

  const startAgentSessionStream = useCallback(
    (sessionId: string) => {
      agentSessionStreamsRef.current[sessionId]?.close();
      const source = new EventSource(`${API_BASE_URL}/agent-sessions/${sessionId}/events/stream`);
      console.log('[Agent] EventSource connected:', sessionId);
      agentSessionStreamsRef.current[sessionId] = source;
      const handleChunk = async (chunk: AgentSessionEvent) => {
        const part = chunk.part || undefined;
        const sessionStatus = chunk.session_status;
        const agentId = chunk.agent_id;

        if (chunk.chunk_type === 'session_snapshot') {
          const snapshot = chunk.session_snapshot;
          if (snapshot) {
            await upsertAgentSessionMessage(snapshot as AgentSession);
          }
          if (agentDeltaFlushRef.current?.rafId) {
            cancelAnimationFrame(agentDeltaFlushRef.current.rafId);
            const pending = agentDeltaFlushRef.current.pending;
            agentDeltaFlushRef.current = null;
            for (const [msgId, pendingDelta] of Object.entries(pending)) {
              useChatStore.getState().appendStreamingDelta(msgId, pendingDelta);
            }
          } else {
            agentDeltaFlushRef.current = null;
          }
          source.close();
          delete agentSessionStreamsRef.current[sessionId];
          Object.keys(streamingDeltaRef.current).forEach((key) => {
            if (key.startsWith('agp_')) delete streamingDeltaRef.current[key];
          });
          setAgentPhase({ phase: '', visible: false });
          return;
        }

        if (sessionStatus || agentId) {
          ensureAgentSessionSnapshot(sessionId, {
            status: sessionStatus || undefined,
            agent_id: agentId || undefined,
            updated_at: chunk.created_at,
          });
        }
        if (chunk.chunk_type === 'phase') {
          const phaseStr = chunk.phase || (chunk.payload?.phase as string) || '';
          if (phaseStr === 'model_thinking') {
            setAgentPhase({ phase: 'model_thinking', visible: true });
} else if (phaseStr === 'tool_execution') {
              setAgentPhase({ phase: 'tool_execution', tool: chunk.tool || (chunk.payload?.tool as string | undefined), detail: (chunk.payload?.detail as string | undefined), visible: true });
            } else if (phaseStr === 'tool_completed') {
              setAgentPhase({ phase: 'tool_completed', tool: chunk.tool || (chunk.payload?.tool as string | undefined), detail: (chunk.payload?.detail as string | undefined), visible: true });
            setTimeout(() => setAgentPhase((prev) => prev.phase === 'tool_completed' ? { ...prev, visible: false } : prev), 1500);
          } else {
            setAgentPhase({ phase: phaseStr, visible: true });
          }
          return;
        }
        const flushAgentDeltas = () => {
          if (agentDeltaFlushRef.current) {
            if (agentDeltaFlushRef.current.rafId) {
              cancelAnimationFrame(agentDeltaFlushRef.current.rafId);
            }
            const pending = { ...agentDeltaFlushRef.current.pending };
            agentDeltaFlushRef.current.pending = {};
            agentDeltaFlushRef.current.rafId = null;
            for (const [msgId, pendingDelta] of Object.entries(pending)) {
              useChatStore.getState().appendStreamingDelta(msgId, pendingDelta);
            }
          }
        };
        if (chunk.chunk_type === 'part_start') {
          flushAgentDeltas();
          setAgentPhase({ phase: 'model_streaming', visible: false });
        }
        if (part) {
          if (chunk.chunk_type === 'part_delta' && (chunk.delta !== undefined || chunk.content !== undefined)) {
            streamingDeltaRef.current[part.id] = { partId: part.id, content: (chunk.content || part.content || '') as string };
            const deltaText = (chunk.delta || '') as string;
            const found = useChatStore.getState().messages.find((m) => m.agent_metadata?.agent_part_id === part.id);
            if (found && deltaText) {
              if (!agentDeltaFlushRef.current) {
                agentDeltaFlushRef.current = { rafId: null, pending: {} };
              }
              const flush = agentDeltaFlushRef.current;
              flush.pending[found.id] = (flush.pending[found.id] || '') + deltaText;
              if (!flush.rafId) {
                flush.rafId = requestAnimationFrame(() => {
                  const pending = { ...flush.pending };
                  flush.pending = {};
                  flush.rafId = null;
                  for (const [msgId, pendingDelta] of Object.entries(pending)) {
                    useChatStore.getState().appendStreamingDelta(msgId, pendingDelta);
                  }
                });
              }
            } else if (found) {
              useChatStore.getState().queueMessageUpdate(found.id, {
                content: (chunk.content || part.content || '') as string,
                isLoading: part.status === 'running',
                agent_metadata: buildAgentPartMetadata(mergeAgentSessionPart(sessionId, part, {
                  status: sessionStatus || undefined,
                  agent_id: agentId || undefined,
                  updated_at: chunk.created_at,
                }), part),
              });
            }
          } else {
            flushAgentDeltas();
            const shouldPersist = chunk.chunk_type !== 'part_start';
            await upsertAgentSessionPartMessage(
              sessionId,
              part,
              {
                status: sessionStatus || undefined,
                agent_id: agentId || undefined,
                updated_at: chunk.created_at,
              },
              { persist: shouldPersist },
            );
          }
        }
        if (chunk.chunk_type === 'tool_call') {
          setAgentPhase({ phase: 'tool_execution', tool: chunk.tool || (chunk.payload?.tool as string | undefined), detail: (chunk.payload?.detail as string | undefined), visible: true });
        } else if (chunk.chunk_type === 'tool_result' || chunk.chunk_type === 'summary' || chunk.chunk_type === 'action') {
          setAgentPhase((prev) => ({ ...prev, visible: false }));
        } else if (chunk.chunk_type === 'error') {
          setAgentPhase({ phase: 'model_thinking_fallback', visible: true });
        }
      };
      source.addEventListener('agent_session_event', (e: MessageEvent) => {
        try { void handleChunk(JSON.parse((e as MessageEvent).data) as AgentSessionEvent); } catch { /* ignore */ }
      });
      source.addEventListener('agent_session_done', () => {
        useChatStore.getState().flushMessageUpdates();
        getAgentSession(sessionId)
          .then((session) => upsertAgentSessionMessage(session))
          .catch(() => undefined);
        source.close();
        delete agentSessionStreamsRef.current[sessionId];
      });
      source.onerror = () => {
        if (agentDeltaFlushRef.current?.rafId) {
          cancelAnimationFrame(agentDeltaFlushRef.current.rafId);
          const pending = agentDeltaFlushRef.current.pending;
          agentDeltaFlushRef.current = null;
          for (const [msgId, pendingDelta] of Object.entries(pending)) {
            useChatStore.getState().appendStreamingDelta(msgId, pendingDelta);
          }
        } else {
          agentDeltaFlushRef.current = null;
        }
        useChatStore.getState().flushMessageUpdates();
        Object.keys(streamingDeltaRef.current).forEach((key) => {
          if (key.startsWith('agp_')) delete streamingDeltaRef.current[key];
        });
        setAgentPhase({ phase: 'connection_lost', visible: true });
        getAgentSession(sessionId)
          .then((session) => {
            upsertAgentSessionMessage(session);
            setAgentPhase({ phase: '', visible: false });
          })
          .catch(() => {
            appendAgentSessionError('Agent 事件流连接中断，暂时无法读取最新执行 transcript。', { id: sessionId });
            setAgentPhase({ phase: '', visible: false });
          });
        source.close();
        delete agentSessionStreamsRef.current[sessionId];
      };
    },
    [appendAgentSessionError, ensureAgentSessionSnapshot, upsertAgentSessionMessage, upsertAgentSessionPartMessage],
  );

  useEffect(() => {
    if (!currentSessionId || currentSessionId.startsWith('local_') || messages.length === 0) return;
    const agentSessionIds = Array.from(
      new Set(
        messages
          .map((message) => message.agent_metadata?.agent_session_id)
          .filter((sessionId): sessionId is string => Boolean(sessionId)),
      ),
    );
    if (!agentSessionIds.length) return;

    agentSessionIds.forEach((sessionId) => {
      const refreshKey = `${currentSessionId}:session:${sessionId}`;
      if (!refreshedAgentSessionsRef.current.has(refreshKey)) {
        refreshedAgentSessionsRef.current.add(refreshKey);
        startAgentSessionStream(sessionId);
      }
    });

  }, [currentSessionId, messages, startAgentSessionStream]);

  const handleAgentSession = useCallback(
    async (
      content: string,
      forceAgent = false,
      options: { agentId?: string; reason?: string; mode?: 'agent'; skipUserMessage?: boolean } = {},
    ) => {
      const goal = content.trim();
      if (!goal) return false;
      if (!forceAgent && !isLikelyAgentGoal(goal)) return false;

      let sessionId = currentSessionId;
      if (!sessionId) {
        const session = await createSession();
        sessionId = session.id;
      }

      if (!options.skipUserMessage) {
        addMessage({ role: 'user', content: goal });
      }
      console.log('[Agent] Starting agent session...', { content, options });
      setCreatingAgentSession(true);
      setRoutingIntent(false);
      let agentSession: AgentSession | undefined;
      try {
        const workspaceContext = selectedWorkspaceLabel !== '未选择工作区'
          ? ` · ${selectedWorkspaceLabel}`
          : '';
        const session = await withTimeout(
          createAgentSession({
            chat_session_id: sessionId && !sessionId.startsWith('local_') ? sessionId : undefined,
            agent_id: options.agentId || selectedPrimaryAgent || 'build',
            title:
              options.mode === 'agent'
                ? `${goal.slice(0, 26) || 'Agent Task'}${workspaceContext}`.slice(0, 64)
                : '',
            project_path: effectiveProjectPath || undefined,
            provider: cloudAIConfig?.provider || undefined,
            model: selectedCloudModel || cloudAIConfig?.model || undefined,
            autonomy_mode: autonomyMode,
          }),
          15000,
          'create_session_timeout',
        );
        agentSession = session;

        if (options.reason) {
          notify.info(options.reason);
        }
        const workspacePrefix = selectedWorkspaceLabel !== '未选择工作区'
          ? `[${selectedWorkspaceLabel}] `
          : '';
        await upsertAgentSessionMessage(session, options.reason ? `${options.reason} ${workspacePrefix}${goal}` : `${workspacePrefix}${goal}`);
        startAgentSessionStream(session.id);
        const started = await withTimeout(
          promptAgentSession(session.id, {
            content: goal,
            provider: cloudAIConfig?.provider || undefined,
            model: selectedCloudModel || cloudAIConfig?.model || undefined,
          }),
          15000,
          'prompt_session_timeout',
        );
        await upsertAgentSessionMessage(started);
        return true;
      } catch (error: any) {
        const isTimeout = error?.message === 'create_session_timeout' || error?.message === 'prompt_session_timeout';
        const detail = isTimeout
          ? '服务器响应超时，请稍后重试'
          : error?.response?.data?.detail?.message ||
            error?.response?.data?.detail ||
            error?.message ||
            'Agent 工作启动失败';
        const fallback = `Agent 工作启动失败：${detail}`;
        notify.error(fallback);
        await appendAgentSessionError(fallback, agentSession || {
          id: sessionId ? `agent_error_${sessionId}_${Date.now()}` : undefined,
          chat_session_id: sessionId && !sessionId.startsWith('local_') ? sessionId : undefined,
          agent_id: options.agentId || selectedPrimaryAgent || 'build',
          title: `${goal.slice(0, 26) || 'Agent Session'}${selectedWorkspaceLabel !== '未选择工作区' ? ` · ${selectedWorkspaceLabel}` : ''}`.slice(0, 64),
          provider: cloudAIConfig?.provider || undefined,
          model: selectedCloudModel || cloudAIConfig?.model || undefined,
          metadata: { autonomy_mode: autonomyMode },
        });
        return true;
      } finally {
        setCreatingAgentSession(false);
      }
    },
    [
      addMessage,
      autonomyMode,
      cloudAIConfig?.model,
      cloudAIConfig?.provider,
      createSession,
      currentSessionId,
      appendAgentSessionError,
      isLikelyAgentGoal,
      effectiveProjectPath,
      selectedCloudModel,
      selectedPrimaryAgent,
      selectedWorkspaceLabel,
      startAgentSessionStream,
      upsertAgentSessionMessage,
    ],
  );

  const handleSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      isAutoScrollEnabledRef.current = true;
      setTimeout(() => scrollToBottom(true, true), 100);

      let tempUserId: string | undefined;
      let tempLoadingId: string | undefined;
      const shouldPreferAgent = routingMode !== 'chat';

      if (routingMode === 'agent' || shouldPreferAgent) {
        if (routingMode === 'agent') {
          const handledByAgent = await handleAgentSession(content, true, { reason: '已按 Agent 模式启动 Build Agent。', mode: 'agent' });
          if (handledByAgent) return;
        }

        if (routingMode === 'auto') {
          console.log('[Routing] Classifying intent via Cloud AI...');
          tempUserId = addMessage({ role: 'user', content: content.trim() });
          tempLoadingId = addMessage({ role: 'assistant', content: '', isLoading: true });
          setRoutingIntent(true);
          try {
            const intent = await withTimeout(
              classifyChatAgentIntent({
                content,
                provider: cloudAIConfig?.provider || undefined,
                model: selectedCloudModel || cloudAIConfig?.model || undefined,
                agent_id: selectedPrimaryAgent || 'build',
                chat_session_id: currentSessionId && !currentSessionId.startsWith('local_') ? currentSessionId : undefined,
                routing_mode: 'auto',
              }),
              INTENT_ROUTING_TIMEOUT_MS,
              'intent_routing_timeout',
            );
            console.log('[Routing] Intent classification result:', intent);
            if (intent.mode === 'agent') {
              removeLocalMessage(tempLoadingId!);
              setRoutingIntent(false);
              const handledByAgent = await handleAgentSession(content, true, {
                agentId: intent.suggested_agent_id || selectedPrimaryAgent || 'build',
                reason: intent.source === 'cloud'
                  ? `云端判断需要 Agent Task：${intent.reason}`
                  : `已识别为开发任务，启动 Agent Task：${intent.reason}`,
                mode: 'agent',
                skipUserMessage: true,
              });
              if (handledByAgent) return;
            }
            if (intent.source === 'fallback') {
              notify.info(intent.reason);
            }
          } catch (error) {
            if (isLikelyAgentGoal(content)) {
              removeLocalMessage(tempLoadingId!);
              setRoutingIntent(false);
              const handledByAgent = await handleAgentSession(content, true, {
                reason: '意图判断失败，已按本地规则启动 Agent Task。',
                mode: 'agent',
                skipUserMessage: true,
              });
              if (handledByAgent) return;
            }
            removeLocalMessage(tempLoadingId!);
            notify.info('意图判断失败，已按普通对话处理。');
          } finally {
            setRoutingIntent(false);
          }
        }
      }

      if (tempUserId) removeLocalMessage(tempUserId);
      if (tempLoadingId) removeLocalMessage(tempLoadingId);
      if (useCloudAI && cloudAIConfig) {
        await sendCloudMessage(
          { prompt: content },
          {
            provider: cloudAIConfig.provider,
            apiKey: cloudAIConfig.api_key,
            keyId: cloudAIConfig.key_id,
            model: selectedCloudModel,
            groupId: cloudAIConfig.group_id,
            baseUrl: cloudAIConfig.base_url,
          },
        );
      } else {
        await sendMessage({ prompt: content });
      }
    },
    [
      addMessage,
      cloudAIConfig,
      currentSessionId,
      deleteMessage,
      handleAgentSession,
      isLikelyAgentGoal,
      removeLocalMessage,
      routingMode,
      scrollToBottom,
      selectedCloudModel,
      selectedPrimaryAgent,
      sendCloudMessage,
      sendMessage,
      useCloudAI,
    ],
  );

  const handleStopCurrentRun = useCallback(async () => {
    if (!activeAgentSessionIds.length) {
      stopStream();
      return;
    }

    try {
      await Promise.all(
        activeAgentSessionIds.map(async (sessionId) => {
          const session = await interruptAgentSession(sessionId);
          agentSessionStreamsRef.current[sessionId]?.close();
          delete agentSessionStreamsRef.current[sessionId];
          await upsertAgentSessionMessage(session);
        }),
      );
      setAgentPhase({ phase: '', visible: false });
      notify.info('已中断 Agent 任务');
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || '中断 Agent 失败';
      notify.error(detail);
    }
  }, [activeAgentSessionIds, stopStream, upsertAgentSessionMessage]);

  const selectedCloudProvider = useMemo(
    () => cloudProviders.find((provider) => provider.provider === cloudAIConfig?.provider),
    [cloudAIConfig?.provider, cloudProviders],
  );

  const cloudProviderOptions = useMemo(
    () =>
      cloudProviders.map((provider) => ({
        id: provider.provider,
        name: `${provider.name || provider.provider} (${provider.provider})`,
      })),
    [cloudProviders],
  );

  const cloudModelOptions = useMemo(() => {
    const models = selectedCloudProvider?.models?.length
      ? selectedCloudProvider.models
      : selectedCloudProvider?.default_model
        ? [selectedCloudProvider.default_model]
        : [];
    return models.map((model) => ({ id: model, name: model }));
  }, [selectedCloudProvider]);

  const handleCloudProviderChange = useCallback(
    async (provider: string) => {
      const selectedProvider = cloudProviders.find((item) => item.provider === provider);
      if (!selectedProvider) return;

      const keyData = await getSavedCloudProviderData(selectedProvider.id).catch(() => ({}));
      const models = keyData.models || selectedProvider.models || [];
      const nextModel = keyData.default_model || selectedProvider.default_model || models[0] || '';
      const config: APIKeyConfig = {
        provider: selectedProvider.provider,
        api_key: '',
        key_id: selectedProvider.id,
        model: nextModel,
        group_id: keyData.group_id || '',
        base_url: keyData.base_url || '',
      };
      setCloudAIConfig(config);
      setSelectedCloudModel(nextModel);
      localStorage.setItem('cloud_ai_config', JSON.stringify(config));
    },
    [cloudProviders],
  );

  const handleCloudModelChange = useCallback(
    (model: string) => {
      setSelectedCloudModel(model);
      if (cloudAIConfig) {
        const nextConfig = { ...cloudAIConfig, model };
        setCloudAIConfig(nextConfig);
        localStorage.setItem('cloud_ai_config', JSON.stringify(nextConfig));
      }
    },
    [],
  );

  const handleRefreshAgentRun = useCallback(
    async (runId: string) => {
      const session = await getAgentSession(runId);
      await upsertAgentSessionMessage(session);
    },
    [upsertAgentSessionMessage],
  );

  const findAgentSessionIdByAction = useCallback((actionId: string) => {
    return useChatStore
      .getState()
      .messages.find((item) => item.agent_metadata?.action_id === actionId && item.agent_metadata?.agent_session_id)
      ?.agent_metadata?.agent_session_id;
  }, []);

  const handleApproveAgentAction = useCallback(
    async (actionId: string) => {
      const sessionId = findAgentSessionIdByAction(actionId);
      if (!sessionId) return;
      const response = await approveAgentAction(actionId);
      await upsertAgentSessionMessage(response.session);
    },
    [findAgentSessionIdByAction, upsertAgentSessionMessage],
  );

  const handleRejectAgentAction = useCallback(
    async (actionId: string) => {
      const sessionId = findAgentSessionIdByAction(actionId);
      if (!sessionId) return;
      const response = await rejectAgentSessionAction(actionId);
      await upsertAgentSessionMessage(response.session);
    },
    [findAgentSessionIdByAction, upsertAgentSessionMessage],
  );

  const handleExecuteAgentAction = useCallback(
    async (actionId: string) => {
      const sessionId = findAgentSessionIdByAction(actionId);
      if (!sessionId) return;
      const response = await executeAgentAction(actionId);
      await upsertAgentSessionMessage(response.session);
      notify.success(response.part.status === 'executed' ? '动作已执行' : '动作执行完成');
    },
    [findAgentSessionIdByAction, upsertAgentSessionMessage],
  );

  const handleRetry = useCallback(
    (messageId: string) => {
      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex === -1) return;

      const userMessage = messages[msgIndex - 1];
      if (!userMessage || userMessage.role !== 'user') return;

      const newMessages = messages.slice(0, msgIndex - 1);
      useChatStore.setState({ messages: newMessages });

      handleSend(userMessage.content);
    },
    [messages, handleSend],
  );

  const handleEditMessage = useCallback(
    async (messageId: string, newContent: string) => {
      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex === -1) return;

      // 将对话截断到这根线，并用新内容重新发送
      const newMessages = messages.slice(0, msgIndex);
      try {
        await replaceCurrentSessionMessages(newMessages);
        await handleSend(newContent);
      } catch (error) {
        const message = error instanceof Error ? error.message : '编辑消息失败';
        notify.error(message);
      }
    },
    [handleSend, messages, replaceCurrentSessionMessages],
  );

  const handleExportChat = useCallback(
    (format: 'markdown' | 'json') => {
      if (messages.length === 0) {
        notify.warning('暂无对话内容');
        return;
      }

      const title = messages.find((m) => m.role === 'user')?.content.slice(0, 20) || '新对话';

      if (format === 'markdown') {
        let content = `# ${title}\n\n`;
        content += `导出时间: ${new Date().toLocaleString('zh-CN')}\n\n---\n\n`;

        for (const msg of messages) {
          const role = msg.role === 'user' ? '用户' : '助手';
          content += `## ${role}\n\n${msg.content}\n\n`;
        }

        const blob = new Blob([content], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title}_${Date.now()}.md`;
        a.click();
        URL.revokeObjectURL(url);
        notify.success('已导出为 Markdown');
      } else {
        const data = {
          title,
          exportedAt: new Date().toISOString(),
          messages,
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title}_${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        notify.success('已导出为 JSON');
      }
    },
    [messages],
  );

  const handleClearChat = useCallback(() => {
    appModal.confirm({
      title: '确认清空',
      content: '确定要清空当前对话吗？',
      okText: '清空',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await clearMessages();
          notify.success('对话已清空');
        } catch (error) {
          const message = error instanceof Error ? error.message : '清空会话失败';
          notify.error(message);
          throw error;
        }
      },
    });
  }, [clearMessages]);

  const handleToggleKnowledge = useCallback(() => {
    const nextUseKnowledge = !settings.useKnowledge;
    const fallbackCollection =
      settings.knowledgeCollection ||
      derived.activeKnowledgeCollection ||
      observed.knowledge.collections[0]?.id;

    updateSettings({
      useKnowledge: nextUseKnowledge,
      knowledgeCollection: nextUseKnowledge ? fallbackCollection : settings.knowledgeCollection,
    });

    if (nextUseKnowledge && fallbackCollection) {
      syncKnowledgeCollection(fallbackCollection);
    }
  }, [
    derived.activeKnowledgeCollection,
    observed.knowledge.collections,
    settings.knowledgeCollection,
    settings.useKnowledge,
    syncKnowledgeCollection,
    updateSettings,
  ]);

  const handleKnowledgeCollectionChange = useCallback(
    (collectionId: string) => {
      updateSettings({ useKnowledge: true });
      syncKnowledgeCollection(collectionId);
    },
    [syncKnowledgeCollection, updateSettings],
  );

  const handleBackendChange = useCallback(
    async (backend: string) => {
      setUseCloudAI(false);
      localStorage.setItem('chat_use_cloud_ai', '0');
      updateSettings({ backend: backend as 'ollama' | 'huggingface' | 'cloud', modelId: '' });
      setInferenceSelection({ backend, modelId: undefined });
      await refreshInference();
    },
    [refreshInference, setInferenceSelection, updateSettings],
  );

  const handleModelChange = useCallback(
    (model: string) => {
      updateSettings({ modelId: model });
      setInferenceSelection({ backend: settings.backend, modelId: model });
    },
    [setInferenceSelection, settings.backend, updateSettings],
  );

  const handleToggleCloudAI = useCallback(() => {
    if (!cloudAIConfig?.api_key && !cloudAIConfig?.key_id) {
      setConfigModalOpen(true);
      return;
    }
    setUseCloudAI((enabled) => !enabled);
  }, [cloudAIConfig?.api_key, cloudAIConfig?.key_id]);

  const handleToggleMemory = useCallback(() => {
    updateSettings({ useMemory: !settings.useMemory });
  }, [settings.useMemory, updateSettings]);

  const virtuosoFooter = useCallback(
    () => (
      <div style={{ paddingBottom: '20px' }}>
        <AgentPhaseIndicator
          phase={agentPhase.phase}
          tool={agentPhase.tool}
          detail={agentPhase.detail}
          visible={agentPhase.visible}
        />
      </div>
    ),
    [
      agentPhase.phase,
      agentPhase.tool,
      agentPhase.visible,
      handleSend,
      isActivelyStreaming,
      isLoading,
    ],
  );

  const virtuosoComponents = useMemo(
    () => ({
      Footer: virtuosoFooter,
    }),
    [virtuosoFooter],
  );

  const modelOptions =
    settings.backend === 'ollama'
      ? observed.inference.ollamaModels.map((m) => ({ id: m.id, name: m.name }))
      : settings.backend === 'llama-cpp'
        ? observed.inference.huggingfaceModels
            .filter((m) => m.name.toLowerCase().includes('.gguf') || m.name.toLowerCase().includes('.ggml'))
            .map((m) => ({ id: m.id, name: m.name }))
        : observed.inference.huggingfaceModels.map((m) => ({ id: m.id, name: m.name }));

  useEffect(() => {
    if (settings.modelId) return;

    if (settings.backend === 'ollama' && observed.inference.ollamaModels.length > 0) {
      const firstOllamaModel = observed.inference.ollamaModels[0];
      if (firstOllamaModel) {
        updateSettings({ modelId: firstOllamaModel.id });
      }
      return;
    }

    if (settings.backend !== 'ollama' && observed.inference.huggingfaceModels.length > 0) {
      const firstHfModel = observed.inference.huggingfaceModels[0];
      if (firstHfModel) {
        updateSettings({ modelId: firstHfModel.id });
      }
    }
  }, [
    observed.inference.huggingfaceModels,
    observed.inference.ollamaModels,
    settings.backend,
    settings.modelId,
    updateSettings,
  ]);

  const activeModeLabel = routingMode === 'agent'
    ? 'Agent Task'
    : routingMode === 'auto' && routingIntent
      ? 'Agent Task 路由中'
      : routingMode === 'chat'
        ? 'Chat'
        : 'Agent Task';
  const activeModelLabel = useCloudAI
    ? selectedCloudModel || '未选择模型'
    : settings.modelId || '未选择模型';
  const agentOptions = primaryAgents.map((agent) => ({ value: agent.id, label: agent.name }));
  const latestAgentMetadata = useMemo(
    () => [...messages].reverse().find((message) => message.agent_metadata)?.agent_metadata,
    [messages],
  );
  const latestAgentSessionId = latestAgentMetadata?.agent_session_id;
  const latestAgentSessionMessages = useMemo(
    () => messages.filter((message) => message.agent_metadata?.agent_session_id === latestAgentSessionId),
    [latestAgentSessionId, messages],
  );
  const latestAgentParts = latestAgentSessionMessages
    .map((message) => message.agent_metadata?.agent_part as AgentPart | undefined)
    .filter((part): part is AgentPart => Boolean(part));
  const latestAgentStatus = latestAgentMetadata?.status || 'idle';
  useEffect(() => {
    if (!latestAgentSessionId) {
      setAgentSessionOverview(null);
      return;
    }
    let cancelled = false;
    getAgentSessionOverview(latestAgentSessionId)
      .then((overview) => {
        if (!cancelled) setAgentSessionOverview(overview);
      })
      .catch(() => {
        if (!cancelled) setAgentSessionOverview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [latestAgentSessionId, messages]);

  const agentFileSummaries = useMemo(() => {
    const depthOf = (path: string) => path.replace(/\\/g, '/').split('/').filter(Boolean).length;
    return (agentSessionOverview?.artifacts || [])
      .map((artifact: AgentArtifact) => ({ ...artifact, depth: depthOf(artifact.path) }))
      .slice(-12)
      .sort((a, b) => a.depth - b.depth || a.path.localeCompare(b.path));
  }, [agentSessionOverview?.artifacts]);

  const agentFileTree = useMemo(() => {
    type TreeNode = {
      name: string;
      path: string;
      kind: 'folder' | 'file';
      children: TreeNode[];
      file?: (typeof agentFileSummaries)[number];
    };

    const root: TreeNode = { name: '', path: '', kind: 'folder', children: [] };

    const insert = (node: TreeNode, segments: string[], file: (typeof agentFileSummaries)[number], fullPath: string): void => {
      if (segments.length === 0) {
        node.children.push({ name: file.path.split('/').pop() || file.path, path: fullPath, kind: 'file', children: [], file });
        return;
      }
      const head = segments[0];
      if (!head) {
        node.children.push({ name: file.path.split('/').pop() || file.path, path: fullPath, kind: 'file', children: [], file });
        return;
      }
      const rest = segments.slice(1);
      const childPath = node.path ? `${node.path}/${head}` : head;
      let child = node.children.find((item) => item.kind === 'folder' && item.name === head) as TreeNode | undefined;
      if (!child) {
        child = { name: head, path: childPath, kind: 'folder', children: [] };
        node.children.push(child);
      }
      if (child) {
        insert(child, rest, file, fullPath);
      }
    };

    for (const file of agentFileSummaries) {
      const normalized = file.path.replace(/\\/g, '/');
      const segments = normalized.split('/').filter(Boolean);
      const name = segments.pop() || normalized;
      insert(root, segments, file, normalized || name);
    }

    const sortTree = (node: TreeNode): TreeNode => {
      const children = node.children
        .map(sortTree)
        .sort((a, b) => {
          if (a.kind !== b.kind) return a.kind === 'folder' ? -1 : 1;
          return a.name.localeCompare(b.name, 'zh-CN');
        });
      return { ...node, children };
    };

    return sortTree(root);
  }, [agentFileSummaries]);

  const defaultExpandedFolders = useMemo(() => {
    const folders = new Set<string>();
    const walk = (node: typeof agentFileTree) => {
      if (node.kind === 'folder' && node.path) folders.add(node.path);
      for (const child of node.children || []) walk(child);
    };
    walk(agentFileTree);
    return folders;
  }, [agentFileTree]);

  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => defaultExpandedFolders);

  useEffect(() => {
    setExpandedFolders((prev) => {
      const next = new Set<string>();
      for (const path of prev) {
        if (defaultExpandedFolders.has(path)) next.add(path);
      }
      if (next.size === 0) {
        defaultExpandedFolders.forEach((path) => next.add(path));
      }
      return next;
    });
  }, [defaultExpandedFolders]);

  const toggleFolder = useCallback((path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const renderTreeNode = useCallback((node: typeof agentFileTree, depth = 0): React.ReactNode => {
    if (node.kind === 'file' && node.file) {
      const file = node.file;
      const statusLower = file.status.toLowerCase();
      const statusTone = /add|new|create|新增/.test(statusLower)
        ? 'success'
        : /delete|remove|removed|删除/.test(statusLower)
          ? 'error'
          : /modify|update|change|edit|fix|modified|修改/.test(statusLower)
            ? 'processing'
            : 'default';
      const relativePath = file.path.replace(/\\/g, '/');
      return (
        <div key={node.path} className={styles.agentFileCard} style={{ ['--file-depth' as any]: String(depth) }}>
          <div className={styles.agentFileTreeRow}>
            <div className={styles.agentFileTreeLine} aria-hidden="true">
              <span className={styles.agentFileTreeBranch} />
              <span className={styles.agentFileTreeDot} data-tone={statusTone} />
            </div>
            <div className={styles.agentFileCardBody}>
              <div className={styles.agentFileCardTop}>
                <div>
                  <div className={styles.agentFilePath}>{node.name}</div>
                  <div className={styles.agentFilePathHint}>{relativePath}</div>
                </div>
                <Tag className={styles.agentFileStatus} color={statusTone}>{file.status || 'modified'}</Tag>
              </div>
              <div className={styles.agentFileSummary}>{file.summary}</div>
              <Collapse
                ghost
                size="small"
                items={[{
                  key: `${file.id}:preview`,
                  label: '代码预览',
                  children: <pre className={styles.agentFilePreview}>{file.preview}</pre>,
                }]}
              />
            </div>
          </div>
        </div>
      );
    }

    if (node.kind === 'folder') {
      const isExpanded = !node.path || expandedFolders.has(node.path);
      const childrenCount = node.children.length;
      const fileCount = node.children.filter((child) => child.kind === 'file').length;
      return (
        <div key={node.path || 'root'} className={styles.agentFolderGroup} style={{ ['--folder-depth' as any]: String(depth) }}>
          {node.path ? (
            <button
              type="button"
              className={styles.agentFolderRow}
              onClick={() => toggleFolder(node.path)}
            >
              <span className={`${styles.agentFolderChevron} ${isExpanded ? styles.agentFolderChevronOpen : ''}`}>▸</span>
              <span className={styles.agentFolderName}>{node.name}</span>
              <Tag className={styles.agentFolderTag}>{childrenCount}</Tag>
              <Tag className={styles.agentFolderSubTag}>{fileCount} files</Tag>
            </button>
          ) : null}
          {isExpanded && (
            <div className={styles.agentFolderChildren}>
              {node.children.map((child) => renderTreeNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    return null;
  }, [expandedFolders, toggleFolder]);

  const contextPanel = (
    <ChatContextPanel
      currentBackend={settings.backend}
      backends={observed.inference.backends}
      onBackendChange={handleBackendChange}
      currentModel={settings.modelId}
      models={modelOptions}
      onModelChange={handleModelChange}
      useCloudAI={useCloudAI}
      onToggleCloudAI={handleToggleCloudAI}
      cloudAIConfigured={!!(cloudAIConfig?.api_key || cloudAIConfig?.key_id)}
      onOpenCloudAIConfig={() => setConfigModalOpen(true)}
      currentCloudProvider={cloudAIConfig?.provider}
      cloudProviders={cloudProviderOptions}
      onCloudProviderChange={handleCloudProviderChange}
      currentCloudModel={selectedCloudModel}
      cloudModels={cloudModelOptions}
      onCloudModelChange={handleCloudModelChange}
      useKnowledge={settings.useKnowledge}
      onToggleKnowledge={handleToggleKnowledge}
      collectionsCount={observed.knowledge.collections.length}
      currentKnowledgeCollection={derived.activeKnowledgeCollection}
      knowledgeCollections={observed.knowledge.collections}
      onKnowledgeCollectionChange={handleKnowledgeCollectionChange}
      useMemory={settings.useMemory}
      onToggleMemory={handleToggleMemory}
      agentModeAvailable={primaryAgents.length > 0}
      agentOptions={agentOptions}
      selectedAgent={selectedPrimaryAgent}
      onAgentChange={setSelectedPrimaryAgent}
      routingMode={routingMode}
      onRoutingModeChange={setRoutingMode}
      routing={routingIntent}
      autonomyMode={autonomyMode}
      onAutonomyModeChange={setAutonomyMode}
      creatingAgentSession={creatingAgentSession}
      isLoading={isLoading}
      isStreaming={isActivelyStreaming}
    />
  );

  const agentFileTreeStats = useMemo(() => ({
    files: agentFileSummaries.length,
    folders: defaultExpandedFolders.size,
  }), [agentFileSummaries.length, defaultExpandedFolders.size]);

  const renderMessageItem = useCallback((index: number, msg: any) => {
    const prevMsg = index > 0 ? messages[index - 1] : null;
    const nextMsg = index < messages.length - 1 ? messages[index + 1] : null;
    const curSession = msg.agent_metadata?.agent_session_id;
    const prevSession = prevMsg?.agent_metadata?.agent_session_id;
    const nextSession = nextMsg?.agent_metadata?.agent_session_id;
    const curIsPart = msg.agent_metadata?.kind === 'agent_part';
    const prevIsPart = prevMsg?.agent_metadata?.kind === 'agent_part';
    const nextIsPart = nextMsg?.agent_metadata?.kind === 'agent_part';
    let agentFlowPosition: 'first' | 'middle' | 'last' | 'only' | null = null;
    if (curIsPart && curSession) {
      const sameSessionPrev = prevIsPart && prevSession === curSession;
      const sameSessionNext = nextIsPart && nextSession === curSession;
      if (sameSessionPrev && sameSessionNext) {
        agentFlowPosition = 'middle';
      } else if (sameSessionPrev && !sameSessionNext) {
        agentFlowPosition = 'last';
      } else if (!sameSessionPrev && sameSessionNext) {
        agentFlowPosition = 'first';
      } else {
        agentFlowPosition = 'only';
      }
    }
    return (
    <ChatMessage
      id={msg.id}
      role={msg.role as 'user' | 'assistant'}
      content={msg.content}
      timestamp={msg.timestamp}
      isLoading={msg.isLoading}
      isStreaming={
        isActivelyStreaming && index === messages.length - 1 && msg.role === 'assistant'
      }
      enableTypewriter={true}
      typewriterSpeed={90}
      onRetry={handleRetry}
      onEdit={handleEditMessage}
      onDelete={deleteMessage}
      knowledge_sources={msg.knowledge_sources}
      retrieval_info={msg.retrieval_info}
      agent_metadata={msg.agent_metadata}
      agentFlowPosition={agentFlowPosition}
      onApproveAgentAction={handleApproveAgentAction}
      onRejectAgentAction={handleRejectAgentAction}
      onExecuteAgentAction={handleExecuteAgentAction}
      onRefreshAgentRun={handleRefreshAgentRun}
    />
    );
  }, [
    isActivelyStreaming,
    messages.length,
    handleRetry,
    handleEditMessage,
    deleteMessage,
    handleApproveAgentAction,
    handleRejectAgentAction,
    handleExecuteAgentAction,
    handleRefreshAgentRun,
  ]);

  const filePanel = (
    <motion.div
      initial={prefersReducedMotion ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : transitions.base}
      className={styles.agentFilePanel}
    >
      <div className={styles.agentFilePanelHeader}>
        <div>
          <div className={styles.agentFilePanelKicker}>Agent Files</div>
          <div className={styles.agentFilePanelTitle}>变更文件</div>
          <div className={styles.agentFilePanelMeta}>
            <span>{agentFileTreeStats.files} 个文件</span>
            <span>{agentFileTreeStats.folders} 个目录</span>
            {workspaceTreeFocusedOnly ? <span>聚焦模式</span> : null}
          </div>
        </div>
        <Tag color={agentFileSummaries.length ? 'processing' : 'default'} className={styles.agentFilePanelTag}>
          {agentFileSummaries.length ? `${agentFileSummaries.length} 个文件` : '暂无变更'}
        </Tag>
      </div>
      <div className={styles.agentFileToolbar}>
        <Button size="small" onClick={() => setWorkspaceTreeFocusedOnly((value) => !value)}>
          {workspaceTreeFocusedOnly ? '显示全部' : '只看变更'}
        </Button>
        <Button size="small" onClick={() => setExpandedFolders(new Set(defaultExpandedFolders))}>展开全部</Button>
        <Button size="small" onClick={() => setExpandedFolders(new Set())}>折叠全部</Button>
      </div>
      {agentFileSummaries.length > 0 ? (
        <div className={styles.agentFileList}>
          {renderTreeNode(agentFileTree)}
        </div>
      ) : (
        <div className={styles.agentFileEmpty}>当 Agent 产生补丁或文件修改时，这里会显示最近的变更摘要与预览。</div>
      )}
    </motion.div>
  );

  const workbenchRunPanel = (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className={styles.projectSidePanel}>
        <div className={styles.projectSideHeader}>
          <div>
            <div className={styles.projectSideKicker}>Current Run</div>
            <div className={styles.projectSideTitle}>{latestAgentMetadata?.active_agent_id || selectedPrimaryAgent || 'build'}</div>
          </div>
          <Tag color={latestAgentStatus === 'completed' ? 'success' : latestAgentStatus === 'failed' ? 'error' : latestAgentStatus.includes('waiting') ? 'warning' : 'processing'}>
            {latestAgentStatus}
          </Tag>
        </div>
        <div className={styles.projectSideStatus}>
          <span>{latestAgentMetadata?.execution_state_message || latestAgentMetadata?.final_summary || '等待新的 Agent 任务。'}</span>
        </div>
      </div>
      {latestAgentParts.length > 0 ? (
        <div className={styles.projectSidePanel}>
          <div className={styles.projectSideTitle}>最近动作</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {latestAgentParts.slice(-4).reverse().map((part) => (
              <div key={part.id} className={styles.agentFileCardBody} style={{ padding: 0 }}>
                <div className={styles.agentFileCardTop}>
                  <span className={styles.agentFilePath} style={{ paddingLeft: 0 }}>{part.title || part.type}</span>
                  <Tag className={styles.agentFileStatus}>{part.status || 'pending'}</Tag>
                </div>
                {part.content ? <div className={styles.agentFileSummary} style={{ paddingLeft: 0 }}>{part.content}</div> : null}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <WorkbenchEmpty description="Agent 启动后，这里会显示最近动作与当前阻塞。" />
      )}
    </div>
  );

  const workbenchProgressPanel = latestAgentParts.length > 0 ? (
    <div style={{ display: 'grid', gap: 10 }}>
      {latestAgentParts.slice(-8).map((part) => (
        <div key={part.id} className={styles.projectSidePanel}>
          <div className={styles.projectSideHeader}>
            <div className={styles.projectSideTitle}>{part.title || part.type}</div>
            <Tag>{part.status || 'pending'}</Tag>
          </div>
          {part.content ? <div className={styles.agentFileSummary} style={{ paddingLeft: 0 }}>{part.content}</div> : null}
        </div>
      ))}
    </div>
  ) : agentSessionOverview?.recent_events?.length ? (
    <div style={{ display: 'grid', gap: 10 }}>
      {agentSessionOverview.recent_events.slice(-8).map((event) => (
        <div key={event.id} className={styles.projectSidePanel}>
          <div className={styles.projectSideHeader}>
            <div className={styles.projectSideTitle}>{event.event_type || 'event'}</div>
            <Tag>{event.created_at || 'recent'}</Tag>
          </div>
          {event.message ? <div className={styles.agentFileSummary} style={{ paddingLeft: 0 }}>{event.message}</div> : null}
        </div>
      ))}
    </div>
  ) : (
    <WorkbenchEmpty description="执行开始后，这里会展示阶段、节点和工具调用。" />
  );

  const workbenchArtifactsPanel = filePanel;

  return (
    <div
      className={styles.chatContainer}
      style={isMobile ? { height: 'calc(100vh - 64px)' } : undefined}
    >
      <ChatHeader
        onNewChat={() => createSession()}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenMemory={() => setMemoryManagerOpen(true)}
        onOpenContextPanel={() => setContextPanelOpen(true)}
        onClearChat={handleClearChat}
        onExportChat={handleExportChat}
        messageCount={messages.length}
        activeModeLabel={activeModeLabel}
        activeModelLabel={activeModelLabel}
      />
      <div className={styles.chatWorkspace}>
        <main className={styles.mainChatPane}>
          <motion.div
            {...sectionMotion}
            className={styles.chatMessagesArea}
            ref={scrollContainerRef}
            onScroll={enableVirtualScroll ? undefined : handleScroll}
          >
            <MotionList className={styles.messagesInner} stagger={0.04}>
              {messages.length === 0 ? (
                <motion.div
                  initial={prefersReducedMotion ? false : { opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={prefersReducedMotion ? { duration: 0 } : { ...transitions.spring, delay: 0.1 }}
                  className={styles.emptyState}
                >
                  <div className={styles.emptyKicker}>AI 工作台</div>
                  <h3 className={styles.emptyTitle}>
                    今天想处理点什么？
                  </h3>
                  <p className={styles.emptyDesc}>
                    普通问题会停留在 Chat，开发任务会进入 Agent Task。
                  </p>
                  
                  <div className={styles.starterSuggestions}>
                    {STARTER_IDEAS.map((idea, i) => (
                      <motion.button
                        key={idea.title}
                        initial={prefersReducedMotion ? false : { opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={prefersReducedMotion ? { duration: 0 } : { delay: 0.18 + i * 0.06, duration: 0.28 }}
                        className={styles.starterBtn}
                        onClick={() => handleSend(idea.desc)}
                      >
                        <div style={{ fontSize: 24, marginBottom: 4 }}>{idea.icon}</div>
                        <div className={styles.starterBtnTitle}>{idea.title}</div>
                        <div className={styles.starterBtnDesc}>{idea.desc}</div>
                      </motion.button>
                    ))}
                  </div>
                </motion.div>
              ) : enableVirtualScroll ? (
                <Virtuoso
                  ref={virtuosoRef}
                  data={messages}
                  itemContent={renderMessageItem}
                  components={virtuosoComponents}
                  initialTopMostItemIndex={initialTopMostItemIndex}
                  rangeChanged={(range) => {
                    visibleRangeStartRef.current = range.startIndex;
                    saveCurrentScrollState({
                      topIndex: clampMessageIndex(range.startIndex, messages.length),
                    });
                  }}
                  atBottomStateChange={(nextIsAtBottom) => {
                    isAutoScrollEnabledRef.current = nextIsAtBottom;
                    setIsAtBottom(nextIsAtBottom);
                    setShowScrollButton(!nextIsAtBottom);
                  }}
                  followOutput={(isAtBottom) => isAtBottom ? 'smooth' : false}
                  style={{ height: '100%' }}
                  alignToBottom
                />
              ) : (
                <MotionList stagger={0.03}>
                  {messages.map((msg, index) => (
                    <React.Fragment key={msg.id}>
                      {renderMessageItem(index, msg)}
                    </React.Fragment>
                  ))}

                  <MotionItem>
                    <AgentPhaseIndicator
                      phase={agentPhase.phase}
                      tool={agentPhase.tool}
                      detail={agentPhase.detail}
                      visible={agentPhase.visible}
                    />
                  </MotionItem>

                  <div ref={messagesEndRef} style={{ height: 1 }} />
                </MotionList>
              )}
            </MotionList>
          </motion.div>

          <AnimatePresence>
            {showScrollButton && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                style={{
                  position: 'absolute',
                  bottom: isMobile ? 108 : 148,
                  right: '50%',
                  transform: 'translateX(50%)',
                  zIndex: 90,
                }}
              >
                <Button
                  shape="circle"
                  icon={<ArrowDownOutlined />}
                  onClick={() => {
                    isAutoScrollEnabledRef.current = true;
                    setShowScrollButton(false);
                    scrollToBottom(true, true);
                  }}
                  style={{
                    boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
                    border: '1px solid var(--border-color)',
                    color: 'var(--text-secondary)',
                    width: 40,
                    height: 40,
                  }}
                />
              </motion.div>
            )}
          </AnimatePresence>

          <ChatInput
            onSend={handleSend}
            onStop={handleStopCurrentRun}
            onClear={handleClearChat}
            disabled={!settings.modelId && !useCloudAI}
            loading={isLoading}
            isStreaming={isActivelyStreaming || isAgentSessionRunning}
            modelId={useCloudAI ? selectedCloudModel : settings.modelId}
            agentModeAvailable={primaryAgents.length > 0}
            routingMode={routingMode}
            routing={routingIntent}
            autonomyMode={autonomyMode}
          />
        </main>

        {isDesktop && (
          <>
            <div
              className={`${styles.splitter} ${resizingSidePanel ? styles.splitterDragging : ''}`}
              role="separator"
              aria-orientation="vertical"
              aria-label="调整聊天区和工具区宽度"
              onPointerDown={handleSplitterPointerDown}
            />
            <div className={styles.sidePanels} style={{ flex: `0 0 ${sidePanelWidth}px` }}>
            <AgentWorkbenchPanel
              changedFiles={agentFileSummaries.length}
              runContent={workbenchRunPanel}
              configContent={React.cloneElement(contextPanel, { embedded: true })}
              progressContent={workbenchProgressPanel}
              artifactsContent={workbenchArtifactsPanel}
            />
            </div>
          </>
        )}
      </div>

      <Drawer
        title="对话设置"
        placement="right"
        width={360}
        open={!isDesktop && contextPanelOpen}
        onClose={() => setContextPanelOpen(false)}
        destroyOnHidden={false}
      >
        <ChatContextPanel
          mobile
          currentBackend={settings.backend}
          backends={observed.inference.backends}
          onBackendChange={handleBackendChange}
          currentModel={settings.modelId}
          models={modelOptions}
          onModelChange={handleModelChange}
          useCloudAI={useCloudAI}
          onToggleCloudAI={handleToggleCloudAI}
          cloudAIConfigured={!!(cloudAIConfig?.api_key || cloudAIConfig?.key_id)}
          onOpenCloudAIConfig={() => setConfigModalOpen(true)}
          currentCloudProvider={cloudAIConfig?.provider}
          cloudProviders={cloudProviderOptions}
          onCloudProviderChange={handleCloudProviderChange}
          currentCloudModel={selectedCloudModel}
          cloudModels={cloudModelOptions}
          onCloudModelChange={handleCloudModelChange}
          useKnowledge={settings.useKnowledge}
          onToggleKnowledge={handleToggleKnowledge}
          collectionsCount={observed.knowledge.collections.length}
          currentKnowledgeCollection={derived.activeKnowledgeCollection}
          knowledgeCollections={observed.knowledge.collections}
          onKnowledgeCollectionChange={handleKnowledgeCollectionChange}
          useMemory={settings.useMemory}
          onToggleMemory={handleToggleMemory}
          agentModeAvailable={primaryAgents.length > 0}
          agentOptions={agentOptions}
          selectedAgent={selectedPrimaryAgent}
          onAgentChange={setSelectedPrimaryAgent}
          routingMode={routingMode}
          onRoutingModeChange={setRoutingMode}
          routing={routingIntent}
          autonomyMode={autonomyMode}
          onAutonomyModeChange={setAutonomyMode}
          creatingAgentSession={creatingAgentSession}
          isLoading={isLoading}
          isStreaming={isActivelyStreaming}
        />
      </Drawer>

      <ChatHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        sessions={sessions.map((s) => ({
          id: s.id,
          title: s.title,
          created_at: s.createdAt,
          updated_at: s.updatedAt,
          message_count: s.messageCount,
          metadata: s.metadata,
          model_id: s.modelId,
        }))}
        onLoadSession={(id) => {
          loadSession(id)
            .then(() => setHistoryOpen(false))
            .catch((error) => {
              const message = error instanceof Error ? error.message : '加载历史会话失败';
              notify.error(message);
            });
        }}
        onDeleteSession={(id) => {
          deleteSession(id).catch((error) => {
            const message = error instanceof Error ? error.message : '删除会话失败';
            notify.error(message);
          });
        }}
      />

      <MemoryManager open={memoryManagerOpen} onClose={() => setMemoryManagerOpen(false)} />

      <Modal
        open={configModalOpen}
        onCancel={() => setConfigModalOpen(false)}
        footer={null}
        width={600}
      >
        <APIKeyManager
          onConfigChange={(config: APIKeyConfig) => {
            setCloudAIConfig(config);
            setSelectedCloudModel(config.model || '');
            void loadCloudAIConfig(true);
          }}
          initialConfig={cloudAIConfig}
        />
      </Modal>
    </div>
  );
};

export default ChatPage;
