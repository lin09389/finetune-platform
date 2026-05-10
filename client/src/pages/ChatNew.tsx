import { Button, Collapse, Drawer, Modal, Tag } from 'antd';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { useNavigate } from 'react-router-dom';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { Input, Select } from 'antd';

import { useChatStream } from '../hooks/chat/useChatStream';
import { useResponsive } from '../hooks/useResponsive';
import { useShallow } from 'zustand/react/shallow';
import { useChatStore } from '../store/chatStore';
import { useTheme } from '../theme';

import ChatHeader from '../components/chat/ChatHeader';
import ChatContextPanel from '../components/chat/ChatContextPanel';
import ChatInput from '../components/chat/ChatInput';
import AgentPhaseIndicator from '../components/chat/AgentPhaseIndicator';
import ChatHistoryDrawer from '../components/ChatHistoryDrawer';
import ChatMessage from '../components/ChatMessage';
import WorkflowStepCard from '../components/chat/WorkflowStepCard';
import ToolEventTimeline from '../components/chat/ToolEventTimeline';
import MemoryManager from '../components/MemoryManager';
import APIKeyManager from '../pages/APIKeyManager';

import { useRuntimeContext } from '../runtime/RuntimeContext';
import {
  API_BASE_URL,
  approveAgentAction,
  approveChatAgentAction,
  approveChatAgentStep,
  classifyChatAgentIntent,
  createAgentSession,
  executeAgentAction,
  executeChatAgentAction,
  getAgentSession,
  getPrimaryAgents,
  getSavedCloudProviderData,
  getSavedCloudProviders,
  getWorkflowTemplates,
  getChatAgentRun,
  interruptAgentSession,
  listWorkspaces,
  promptAgentSession,
  rejectAgentAction as rejectAgentSessionAction,
  rejectChatAgentAction,
} from '../services/api';
import type { AgentInfo, AgentPart, AgentSession, AgentSessionEvent, ChatAgentRun, SavedCloudProvider, WorkflowAction, WorkflowStep, WorkflowTemplate, WorkspaceSummary } from '../services/api';
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
const INTENT_ROUTING_TIMEOUT_MS = 1800;
const CHAT_WORKSPACE_ID_STORAGE_KEY = 'chat_workspace_id_v1';
const CHAT_PROJECT_PATH_STORAGE_KEY = 'chat_project_path_v1';

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
  const { theme, toggleTheme } = useTheme();
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
  const [workflowTemplates, setWorkflowTemplates] = useState<WorkflowTemplate[]>([]);
  const [selectedWorkflowTemplate, setSelectedWorkflowTemplate] = useState('software_delivery');
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
  const [creatingWorkflow, setCreatingWorkflow] = useState(false);
  const [availableWorkspaces, setAvailableWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>(() => localStorage.getItem(CHAT_WORKSPACE_ID_STORAGE_KEY) || '');
  const [workspaceProjectPath, setWorkspaceProjectPath] = useState<string>(() => localStorage.getItem(CHAT_PROJECT_PATH_STORAGE_KEY) || '');
  const [workflowSteps, setWorkflowSteps] = useState<WorkflowStep[]>([]);
  const [workflowTitle, setWorkflowTitle] = useState('Workflow Report');
  const [workflowStatus, setWorkflowStatus] = useState('idle');
  const [toolEvents, setToolEvents] = useState<Array<{ id: string; toolName: string; status: string; summary?: string; agentId?: string; durationMs?: number; error?: string; stepId?: string }>>([]);
  const chatAgentStreamsRef = useRef<Record<string, EventSource>>({});
  const agentSessionStreamsRef = useRef<Record<string, EventSource>>({});
  const agentSessionStateRef = useRef<Record<string, AgentSession>>({});
  const refreshedAgentRunsRef = useRef<Set<string>>(new Set());
  const refreshedAgentSessionsRef = useRef<Set<string>>(new Set());
  const streamingDeltaRef = useRef<Record<string, { partId: string; content: string }>>({});
  const [agentPhase, setAgentPhase] = useState<{ phase: string; tool?: string; visible: boolean }>({ phase: '', visible: false });
  const navigate = useNavigate();

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
  const autoScrollFrameRef = useRef<number | null>(null);
  const pendingAutoScrollRef = useRef(false);

  const saveCurrentScrollState = useCallback(
    (overrides?: Partial<StoredChatScrollState>) => {
      if (!currentSessionId || messages.length === 0) return;
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
  const workspacePathStatus = useMemo(() => {
    const path = workspaceProjectPath.trim();
    if (!path) {
      return { tone: 'default' as const, text: '未填写路径，将使用所选工作区或默认项目根目录。' };
    }
    if (selectedWorkspace?.local_path && selectedWorkspace.local_path.trim() === path) {
      return { tone: 'success' as const, text: '路径与当前工作区一致。' };
    }
    return { tone: 'warning' as const, text: '当前为自定义路径，Agent 将使用这里的目录执行。' };
  }, [selectedWorkspace?.local_path, workspaceProjectPath]);

  useEffect(() => {
    setIsAtBottom(shouldRestoreToBottom);
    isAutoScrollEnabledRef.current = shouldRestoreToBottom;
    setShowScrollButton(messages.length > 0 && !shouldRestoreToBottom);
  }, [currentSessionId, messages.length, shouldRestoreToBottom]);

  useEffect(() => () => {
    saveCurrentScrollState();
  }, [saveCurrentScrollState]);

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
      loadWorkflowTemplates(),
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
    Object.values(chatAgentStreamsRef.current).forEach((source) => source.close());
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
    let cancelled = false;
    const loadWorkspaceOptions = async () => {
      try {
        const workspaces = await listWorkspaces();
        if (cancelled) return;
        setAvailableWorkspaces(workspaces);
        if (!selectedWorkspaceId) return;
        const selected = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);
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

  const loadWorkflowTemplates = async () => {
    try {
      const templates = await getWorkflowTemplates();
      setWorkflowTemplates(templates || []);
      if (!templates?.some((template: WorkflowTemplate) => template.id === selectedWorkflowTemplate)) {
        setSelectedWorkflowTemplate('software_delivery');
      }
    } catch {
      setWorkflowTemplates([]);
    }
  };

  const loadPrimaryAgents = async () => {
    try {
      const agents = await getPrimaryAgents();
      setPrimaryAgents(agents || []);
      const saved = localStorage.getItem('chat_primary_agent') || 'build';
      const fallback = agents?.some((agent) => agent.id === saved) ? saved : agents?.[0]?.id || 'build';
      setSelectedPrimaryAgent(fallback);
    } catch {
      setPrimaryAgents([]);
      setSelectedPrimaryAgent('build');
    }
  };

  const isLikelyAgentGoal = useCallback((content: string) => {
    const text = content.trim().toLowerCase();
    if (!text) return false;
    if (['不要执行', '只讨论', '只分析', '解释一下', '帮我解释', '什么是', '为什么'].some((keyword) => text.includes(keyword))) {
      return false;
    }
    return [
      '修改',
      '新增',
      '实现',
      '修复',
      '重构',
      '优化代码',
      '给当前项目',
      '代码里',
      '页面',
      '接口',
      '组件',
      '后端',
      '前端',
      '跑测试',
      '运行测试',
      'typecheck',
      'pytest',
      'npm run',
      '让agent做',
      '自动处理',
      '补丁',
      '搜索项目',
      '写脚本',
      '排查报错',
      '排查问题',
      '运行命令',
      '执行补丁',
    ].some((keyword) => text.includes(keyword));
  }, []);

  const buildAgentMetadata = useCallback(
    (run: ChatAgentRun, kind: any, action?: WorkflowAction) => {
      const toolCalls = run.observability?.tool_calls || [];
      const workflowMetadata = (run.workflow?.metadata || {}) as Record<string, any>;
      const blocked = [...toolCalls]
        .reverse()
        .find((item) => item.status === 'blocked' || item.permission_decision === 'ask' || item.permission_decision === 'deny');
      return {
        agent_run_id: run.id,
        workflow_id: run.workflow_id,
        kind,
        status: action?.status || run.status,
        step_id: run.workflow?.steps?.find((step) => step.status === 'awaiting_approval')?.step_id,
        action_id: action?.id,
        action_type: action?.action_type,
        can_approve: kind === 'agent_approval_request' || action?.status === 'pending_approval',
        can_execute: action?.status === 'approved',
        details_url: run.details_url,
        active_agent_id: run.active_agent_id || run.workflow?.active_agent_id,
        subagent_runs: run.subagent_runs || run.observability?.subagent_runs || [],
        workflow: run.workflow,
        observability: run.observability,
        tool_calls: toolCalls,
        permission_pending: Boolean(
          toolCalls.some((item) => item.permission_decision === 'ask' && item.status === 'blocked'),
        ),
        latest_blocked_tool: blocked?.tool_name,
        execution_state: run.execution_state || workflowMetadata.execution_state,
        execution_state_message: run.execution_state_message || workflowMetadata.execution_state_message,
        final_summary: run.final_summary,
        recoverable: run.recoverable,
        model_protocol_status: run.model_protocol_status || workflowMetadata.model_protocol_status,
        last_model_output_preview: run.last_model_output_preview || workflowMetadata.last_model_output_preview,
        parse_repair_count: run.parse_repair_count ?? workflowMetadata.parse_repair_count,
        fallback_summary_used: run.fallback_summary_used ?? workflowMetadata.fallback_summary_used,
        acceptance_report: run.acceptance_report || workflowMetadata.acceptance_report,
        acceptance_report_source: run.acceptance_report_source || workflowMetadata.acceptance_report_source,
        acceptance_report_raw: run.acceptance_report_raw || workflowMetadata.acceptance_report_raw,
        blocked_state: workflowMetadata.blocked_state || run.blocked_state,
        autonomy_mode: (run.auto_execution_policy?.mode || workflowMetadata.autonomy_mode || workflowMetadata.auto_execution_policy?.mode || 'safe_auto') as 'safe_auto' | 'confirm_all' | 'read_only',
        auto_execution_policy: run.auto_execution_policy || workflowMetadata.auto_execution_policy,
        repair_attempts: workflowMetadata.repair_attempts,
        max_repair_attempts: workflowMetadata.max_repair_attempts,
        action,
        event: run.latest_event,
        latest_event: run.latest_event,
        latest_tool_call: run.latest_tool_call,
        latest_action: run.latest_action,
      };
    },
    [],
  );

  const workflowStepFromRun = useCallback((run: ChatAgentRun): WorkflowStep | null => {
    const workflow = run.workflow;
    if (!workflow) return null;
    const steps = workflow.steps || [];
    if (!steps.length) return null;
    const activeStep = [...steps].reverse().find((step) =>
      step.status !== 'completed'
    ) || steps[steps.length - 1];
    
    if (!activeStep) return null;

    const latestEvent: any = run.latest_event || {};
    const latestToolCall: any = run.latest_tool_call || {};
    const latestAction: any = run.latest_action || {};
    const problem = run.blocked_state?.summary
      || run.execution_state_message
      || activeStep.description
      || run.summary
      || run.final_summary
      || latestEvent?.message
      || '工作流已启动';
    const reason = run.blocked_state?.reason
      || run.execution_state_message
      || latestEvent?.message
      || latestToolCall?.result_summary
      || latestToolCall?.sanitized_model_output
      || '';
    const fix = run.acceptance_report?.next_action
      || latestAction?.title
      || latestAction?.description
      || latestToolCall?.result_summary
      || latestToolCall?.sanitized_model_output
      || '';
    return {
      id: activeStep.id,
      step_id: activeStep.step_id,
      workflow_id: activeStep.workflow_id,
      step_key: activeStep.step_key,
      agent_id: activeStep.agent_id,
      legacy_role: activeStep.legacy_role,
      title: activeStep.title,
      description: activeStep.description,
      status: latestEvent?.event_type === 'approval_needed' ? 'waiting_approval' : (run.status || activeStep.status),
      requires_approval: activeStep.requires_approval,
      input_data: {
        latest_event: latestEvent,
        latest_tool_call: latestToolCall,
      },
      output_data: {
        problem,
        reason,
        fix,
        summary: run.summary || run.final_summary || run.execution_state_message || '',
      },
      output: {
        problem,
        reason,
        fix,
        summary: run.summary || run.final_summary || run.execution_state_message || '',
      },
      error: run.blocked_state?.message || run.execution_state_message || undefined,
    };
  }, []);

  const workflowStepCards = useMemo(() => {
    const steps = workflowSteps.length > 0 ? workflowSteps : [];
    return steps.map((step, index) => (
      <WorkflowStepCard
        key={step.id || step.step_id || String(index)}
        index={index + 1}
        step={step}
        active={workflowStatus === 'running' && index === steps.length - 1}
        toolEvents={toolEvents.filter((event) => event.stepId === step.step_id || event.stepId === step.id)}
      />
    ));
  }, [toolEvents, workflowStatus, workflowSteps]);

  const pushToolEvent = useCallback((event: { id: string; toolName: string; status: string; summary?: string; agentId?: string; durationMs?: number; error?: string; stepId?: string }) => {
    setToolEvents((prev) => {
      const nextMap = new Map<string, typeof event>();
      for (const item of prev) nextMap.set(item.id, item);
      nextMap.set(event.id, event);
      return Array.from(nextMap.values()).slice(-12);
    });
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
          state.updateMessage(existing.id, {
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
        state.updateMessage(existing.id, {
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

  const upsertAgentMessages = useCallback(
    async (run: ChatAgentRun) => {
      if (!run.workflow_id) return;
      const state = useChatStore.getState();
      const current = state.messages;
      const existingRun = current.find(
        (message) => message.agent_metadata?.agent_run_id === run.id && message.agent_metadata.kind === 'agent_run_card',
      );
      const runContent = run.summary || `Agent 状态：${run.status}`;
      if (existingRun) {
        state.updateMessage(existingRun.id, {
          content: runContent,
          isLoading: false,
          agent_metadata: buildAgentMetadata(run, 'agent_run_card'),
        });
      } else {
        state.addMessage({
          role: 'assistant',
          content: runContent,
          agent_metadata: buildAgentMetadata(run, 'agent_run_card'),
        });
      }

      const waitingStep = run.workflow?.steps?.find((step) => step.status === 'awaiting_approval');
      if (waitingStep) {
        const existingApproval = useChatStore
          .getState()
          .messages.find((message) => message.agent_metadata?.step_id === waitingStep.step_id);
        const content = waitingStep.output?.summary || waitingStep.output_data?.summary || `等待审批：${waitingStep.title}`;
        if (existingApproval) {
          state.updateMessage(existingApproval.id, {
            content,
            agent_metadata: buildAgentMetadata(run, 'agent_approval_request'),
          });
        } else {
          state.addMessage({
            role: 'assistant',
            content,
            agent_metadata: buildAgentMetadata(run, 'agent_approval_request'),
          });
        }
      }

      for (const action of run.observability?.actions || []) {
        const existingAction = useChatStore
          .getState()
          .messages.find((message) => message.agent_metadata?.action_id === action.id);
        const content = `${action.action_type === 'patch' ? '补丁建议' : '命令建议'}：${action.title}`;
        const kind = action.executions?.length ? 'agent_action_execution' : 'agent_action_proposal';
        if (existingAction) {
          state.updateMessage(existingAction.id, {
            content,
            agent_metadata: buildAgentMetadata(run, kind, action),
          });
        } else {
          state.addMessage({
            role: 'assistant',
            content,
            agent_metadata: buildAgentMetadata(run, kind, action),
          });
        }
      }

      await persistAgentMessages();
    },
    [buildAgentMetadata, persistAgentMessages],
  );

  const startChatAgentStream = useCallback(
    (runId: string) => {
      chatAgentStreamsRef.current[runId]?.close();
      const source = new EventSource(`${API_BASE_URL}/chat-agent/runs/${runId}/events/stream`);
      chatAgentStreamsRef.current[runId] = source;
      source.addEventListener('chat_agent_event', async () => {
        const run = await getChatAgentRun(runId).catch(() => null);
        if (run) {
          const nextWorkflowStep = workflowStepFromRun(run);
          if (nextWorkflowStep) {
            setWorkflowTitle(run.workflow?.title || (run as any).title || 'Workflow Report');
            setWorkflowStatus(run.status || run.execution_state || 'running');
            setWorkflowSteps((prev) => {
              const nextMap = new Map<string, WorkflowStep>();
              for (const step of prev) {
                nextMap.set(`${step.workflow_id}:${step.step_id || step.id}`, step);
              }
              nextMap.set(`${nextWorkflowStep.workflow_id}:${nextWorkflowStep.step_id || nextWorkflowStep.id}`, nextWorkflowStep);
              return Array.from(nextMap.values()).sort((a, b) => {
                const aActive = a.status === 'running' || a.status === 'waiting_approval' || a.status === 'blocked';
                const bActive = b.status === 'running' || b.status === 'waiting_approval' || b.status === 'blocked';
                if (aActive !== bActive) return aActive ? 1 : -1;
                return String(a.step_id || a.id).localeCompare(String(b.step_id || b.id));
              });
            });
          }
          const latestToolCall = run.latest_tool_call;
          if (latestToolCall?.tool_name) {
            pushToolEvent({
              id: `${run.id}:${latestToolCall.id || latestToolCall.tool_name}:${latestToolCall.status || 'pending'}`,
              toolName: latestToolCall.tool_name,
              status: latestToolCall.status || 'pending',
              summary: latestToolCall.result_summary || latestToolCall.sanitized_model_output || latestToolCall.raw_model_output,
              agentId: run.active_agent_id || run.workflow?.active_agent_id,
              durationMs: latestToolCall.duration_ms,
              error: latestToolCall.error,
              stepId: latestToolCall.step_id,
            });
          }
          for (const toolCall of run.observability?.tool_calls || []) {
            if (!toolCall?.tool_name) continue;
            pushToolEvent({
              id: `${run.id}:${toolCall.id || toolCall.tool_name}:${toolCall.status || 'pending'}`,
              toolName: toolCall.tool_name,
              status: toolCall.status || 'pending',
              summary: toolCall.result_summary || toolCall.sanitized_model_output || toolCall.raw_model_output,
              agentId: toolCall.agent_id || run.active_agent_id || run.workflow?.active_agent_id,
              durationMs: toolCall.duration_ms,
              error: toolCall.error,
              stepId: toolCall.step_id,
            });
          }
          await upsertAgentMessages(run);
        }
      });
      source.onerror = () => {
        source.close();
        delete chatAgentStreamsRef.current[runId];
      };
    },
    [upsertAgentMessages],
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
            setAgentPhase({ phase: 'tool_execution', tool: chunk.tool || (chunk.payload?.tool as string | undefined), visible: true });
          } else if (phaseStr === 'tool_completed') {
            setAgentPhase({ phase: 'tool_completed', tool: chunk.tool || (chunk.payload?.tool as string | undefined), visible: true });
            setTimeout(() => setAgentPhase((prev) => prev.phase === 'tool_completed' ? { ...prev, visible: false } : prev), 1500);
          } else {
            setAgentPhase({ phase: phaseStr, visible: true });
          }
          return;
        }
        if (chunk.chunk_type === 'part_start') {
          setAgentPhase({ phase: 'model_streaming', visible: false });
        }
        if (part) {
          if (chunk.chunk_type === 'part_delta' && (chunk.delta !== undefined || chunk.content !== undefined)) {
            streamingDeltaRef.current[part.id] = { partId: part.id, content: (chunk.content || part.content || '') as string };
          }
          const shouldPersist = chunk.chunk_type !== 'part_delta' && chunk.chunk_type !== 'part_start';
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
        if (chunk.chunk_type === 'tool_call') {
          setAgentPhase({ phase: 'tool_execution', tool: chunk.tool || (chunk.payload?.tool as string | undefined), visible: true });
        } else if (chunk.chunk_type === 'tool_result' || chunk.chunk_type === 'summary' || chunk.chunk_type === 'action') {
          setAgentPhase((prev) => ({ ...prev, visible: false }));
        } else if (chunk.chunk_type === 'error') {
          setAgentPhase({ phase: 'model_thinking_fallback', visible: true });
        }
      };
      source.addEventListener('agent_session_event', (e: MessageEvent) => {
        try { void handleChunk(JSON.parse((e as MessageEvent).data) as AgentSessionEvent); } catch { /* ignore */ }
      });
      source.onerror = () => {
        Object.keys(streamingDeltaRef.current).forEach((key) => {
          if (key.startsWith('agp_')) delete streamingDeltaRef.current[key];
        });
        setAgentPhase({ phase: '', visible: false });
        getAgentSession(sessionId)
          .then((session) => upsertAgentSessionMessage(session))
          .catch(() => appendAgentSessionError('Agent 事件流连接中断，暂时无法读取最新执行 transcript。', { id: sessionId }));
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
    const runIds = Array.from(
      new Set(
        messages
          .filter((message) => !message.agent_metadata?.agent_session_id)
          .map((message) => message.agent_metadata?.agent_run_id)
          .filter((runId): runId is string => Boolean(runId)),
      ),
    );
    if (!runIds.length && !agentSessionIds.length) return;

    agentSessionIds.forEach((sessionId) => {
      const refreshKey = `${currentSessionId}:session:${sessionId}`;
      if (!refreshedAgentSessionsRef.current.has(refreshKey)) {
        refreshedAgentSessionsRef.current.add(refreshKey);
        startAgentSessionStream(sessionId);
      }
    });

    runIds.forEach((runId) => {
      const refreshKey = `${currentSessionId}:${runId}`;
      if (!refreshedAgentRunsRef.current.has(refreshKey)) {
        refreshedAgentRunsRef.current.add(refreshKey);
        getChatAgentRun(runId)
          .then(async (run) => {
            await upsertAgentMessages(run);
          })
          .catch(() => {
            refreshedAgentRunsRef.current.delete(refreshKey);
          });
      }
    });
  }, [currentSessionId, messages, startAgentSessionStream, upsertAgentMessages]);

  const handleAgentWorkflow = useCallback(
    async (
      content: string,
      forceAgent = false,
      options: { agentId?: string; templateId?: string; reason?: string; mode?: 'agent' | 'workflow' } = {},
    ) => {
      const goal = content.trim();
      if (!goal) return false;
      if (!forceAgent && !isLikelyAgentGoal(goal)) return false;

      let sessionId = currentSessionId;
      if (!sessionId) {
        const session = await createSession();
        sessionId = session.id;
      }

      addMessage({ role: 'user', content: goal });
      console.log('[Agent] Starting workflow creation...', { content, options });
      setCreatingWorkflow(true);
      setRoutingIntent(false);
      let agentSession: AgentSession | undefined;
      try {
        const workspaceContext = selectedWorkspaceLabel !== '未选择工作区'
          ? ` · ${selectedWorkspaceLabel}`
          : '';
        const session = await createAgentSession({
          chat_session_id: sessionId && !sessionId.startsWith('local_') ? sessionId : undefined,
          agent_id: options.agentId || selectedPrimaryAgent || 'build',
          title:
            options.mode === 'workflow'
              ? `${goal.slice(0, 26) || 'Workflow Run'}${workspaceContext}`.slice(0, 64)
              : `${goal.slice(0, 26) || 'Agent Task'}${workspaceContext}`.slice(0, 64),
          project_path: workspaceProjectPath.trim() || undefined,
          provider: cloudAIConfig?.provider || undefined,
          model: selectedCloudModel || cloudAIConfig?.model || undefined,
          autonomy_mode: autonomyMode,
        });
        agentSession = session;

        if (options.reason) {
          notify.info(options.reason);
        }
        const workspacePrefix = selectedWorkspaceLabel !== '未选择工作区'
          ? `[${selectedWorkspaceLabel}] `
          : '';
        await upsertAgentSessionMessage(session, options.reason ? `${options.reason} ${workspacePrefix}${goal}` : `${workspacePrefix}${goal}`);
        startAgentSessionStream(session.id);
        const started = await promptAgentSession(session.id, {
          content: goal,
          provider: cloudAIConfig?.provider || undefined,
          model: selectedCloudModel || cloudAIConfig?.model || undefined,
        });
        await upsertAgentSessionMessage(started);
        notify.success('Agent 已开始工作');
        return true;
      } catch (error: any) {
        const detail =
          error?.response?.data?.detail?.message ||
          error?.response?.data?.detail ||
          error?.message ||
          'Agent 工作启动失败';
        const fallback = `${options.mode === 'workflow' ? 'Workflow 运行启动失败' : 'Agent 工作启动失败'}：${detail}`;
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
        setCreatingWorkflow(false);
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
      selectedCloudModel,
      selectedPrimaryAgent,
      startAgentSessionStream,
      upsertAgentSessionMessage,
    ],
  );

  const handleSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      isAutoScrollEnabledRef.current = true;
      setTimeout(() => scrollToBottom(true, true), 100);

      const shouldPreferWorkflow = routingMode !== 'chat';

      if (routingMode === 'agent' || shouldPreferWorkflow) {
        if (routingMode === 'agent') {
          const handledByAgent = await handleAgentWorkflow(content, true, { reason: '已按 Agent 模式启动 Build Agent。', mode: 'agent' });
          if (handledByAgent) return;
        }

        if (routingMode === 'auto') {
          console.log('[Routing] Classifying intent via Cloud AI...');
          setRoutingIntent(true);
          try {
            const intent = await withTimeout(
              classifyChatAgentIntent({
                content,
                provider: cloudAIConfig?.provider || undefined,
                model: selectedCloudModel || cloudAIConfig?.model || undefined,
                agent_id: selectedPrimaryAgent || 'build',
                template_id: selectedWorkflowTemplate || 'software_delivery',
                chat_session_id: currentSessionId && !currentSessionId.startsWith('local_') ? currentSessionId : undefined,
                routing_mode: 'auto',
              }),
              INTENT_ROUTING_TIMEOUT_MS,
              'intent_routing_timeout',
            );
            console.log('[Routing] Intent classification result:', intent);
            if (intent.mode === 'workflow') {
              setRoutingIntent(false);
              const handledByWorkflow = await handleAgentWorkflow(content, true, {
                agentId: intent.suggested_agent_id || selectedPrimaryAgent || 'build',
                templateId: intent.suggested_template_id || selectedWorkflowTemplate || 'software_delivery',
                reason: intent.source === 'cloud'
                  ? `云端判断需要 Workflow Run：${intent.reason}`
                  : `已识别为流程编排任务，启动 Workflow Run：${intent.reason}`,
                mode: 'workflow',
              });
              if (handledByWorkflow) return;
            }
            if (intent.mode === 'agent') {
              setRoutingIntent(false);
              const handledByAgent = await handleAgentWorkflow(content, true, {
                agentId: intent.suggested_agent_id || selectedPrimaryAgent || 'build',
                templateId: intent.suggested_template_id || selectedWorkflowTemplate || 'software_delivery',
                reason: intent.source === 'cloud'
                  ? `云端判断需要 Agent Task：${intent.reason}`
                  : `已识别为开发任务，启动 Agent Task：${intent.reason}`,
                mode: 'agent',
              });
              if (handledByAgent) return;
            }
            if (intent.source === 'fallback') {
              notify.info(intent.reason);
            }
          } catch (error) {
            if (isLikelyAgentGoal(content)) {
              setRoutingIntent(false);
              const handledByAgent = await handleAgentWorkflow(content, true, {
                reason: '意图判断失败，已按本地规则启动 Agent Task。',
                mode: 'agent',
              });
              if (handledByAgent) return;
            }
            notify.info('意图判断失败，已按普通对话处理。');
          } finally {
            setRoutingIntent(false);
          }
        }
      }

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
      cloudAIConfig,
      currentSessionId,
      handleAgentWorkflow,
      isLikelyAgentGoal,
      routingMode,
      scrollToBottom,
      selectedCloudModel,
      selectedPrimaryAgent,
      selectedWorkflowTemplate,
      sendCloudMessage,
      sendMessage,
      useCloudAI,
    ],
  );

  const handleCreateWorkflow = useCallback(
    async (content: string) => {
      const goal = content.trim();
      if (!goal) {
        notify.warning('请先输入 Agent 目标');
        return;
      }

      setCreatingWorkflow(true);
      try {
        await handleAgentWorkflow(goal, true);
      } catch (error: any) {
        notify.error(error?.response?.data?.detail || 'Agent 工作启动失败');
      } finally {
        setCreatingWorkflow(false);
      }
    },
    [handleAgentWorkflow],
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

  const workflowTemplateOptions = useMemo(
    () =>
      (workflowTemplates.length
        ? workflowTemplates
        : [{ id: 'software_delivery', name: 'AI 软件交付流程' } as WorkflowTemplate]
      ).map((template) => ({ value: template.id, label: template.name })),
    [workflowTemplates],
  );

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

  const refreshAgentRunByAction = useCallback(
    async (actionId: string) => {
      const message = useChatStore
        .getState()
        .messages.find((item) => item.agent_metadata?.action_id === actionId);
      const runId = message?.agent_metadata?.agent_run_id;
      if (!runId) return;
      const run = await getChatAgentRun(runId);
      await upsertAgentMessages(run);
    },
    [upsertAgentMessages],
  );

  const handleRefreshAgentRun = useCallback(
    async (runId: string) => {
      const sessionMessage = useChatStore.getState().messages.find((item) => item.agent_metadata?.agent_session_id === runId);
      if (sessionMessage) {
        const session = await getAgentSession(runId);
        await upsertAgentSessionMessage(session);
        return;
      }
      const run = await getChatAgentRun(runId);
      await upsertAgentMessages(run);
      if (run.recoverable && ['created', 'running', 'planning', 'implementing', 'reviewing'].includes(run.status)) {
        startChatAgentStream(run.id);
      }
    },
    [startChatAgentStream, upsertAgentMessages, upsertAgentSessionMessage],
  );

  const findAgentRunIdByStep = useCallback((stepId: string) => {
    return useChatStore
      .getState()
      .messages.find((item) => item.agent_metadata?.step_id === stepId)?.agent_metadata?.agent_run_id;
  }, []);

  const findAgentRunIdByAction = useCallback((actionId: string) => {
    return useChatStore
      .getState()
      .messages.find((item) => item.agent_metadata?.action_id === actionId)?.agent_metadata?.agent_run_id;
  }, []);

  const findAgentSessionIdByAction = useCallback((actionId: string) => {
    return useChatStore
      .getState()
      .messages.find((item) => item.agent_metadata?.action_id === actionId && item.agent_metadata?.agent_session_id)
      ?.agent_metadata?.agent_session_id;
  }, []);

  const handleApproveAgentStep = useCallback(
    async (stepId: string) => {
      const runId = findAgentRunIdByStep(stepId);
      if (runId) {
        startChatAgentStream(runId);
      }
      const run = await approveChatAgentStep(stepId, { approved: true });
      await upsertAgentMessages(run);
      startChatAgentStream(run.id);
    },
    [findAgentRunIdByStep, startChatAgentStream, upsertAgentMessages],
  );

  const handleApproveAgentAction = useCallback(
    async (actionId: string) => {
      const sessionId = findAgentSessionIdByAction(actionId);
      if (sessionId) {
        const response = await approveAgentAction(actionId);
        await upsertAgentSessionMessage(response.session);
        return;
      }
      const runId = findAgentRunIdByAction(actionId);
      if (runId) {
        startChatAgentStream(runId);
      }
      await approveChatAgentAction(actionId);
      await refreshAgentRunByAction(actionId);
    },
    [findAgentRunIdByAction, findAgentSessionIdByAction, refreshAgentRunByAction, startChatAgentStream, upsertAgentSessionMessage],
  );

  const handleRejectAgentAction = useCallback(
    async (actionId: string) => {
      const sessionId = findAgentSessionIdByAction(actionId);
      if (sessionId) {
        const response = await rejectAgentSessionAction(actionId);
        await upsertAgentSessionMessage(response.session);
        return;
      }
      await rejectChatAgentAction(actionId);
      await refreshAgentRunByAction(actionId);
    },
    [findAgentSessionIdByAction, refreshAgentRunByAction, upsertAgentSessionMessage],
  );

  const handleExecuteAgentAction = useCallback(
    async (actionId: string) => {
      const sessionId = findAgentSessionIdByAction(actionId);
      if (sessionId) {
        const response = await executeAgentAction(actionId);
        await upsertAgentSessionMessage(response.session);
        notify.success(response.part.status === 'executed' ? '动作已执行' : '动作执行完成');
        return;
      }
      const runId = findAgentRunIdByAction(actionId);
      if (runId) {
        startChatAgentStream(runId);
      }
      const action = await executeChatAgentAction(actionId);
      await refreshAgentRunByAction(actionId);
      if (action.status === 'failed') {
        notify.error('动作执行失败，已在聊天卡片中展示输出');
      } else {
        notify.success('动作已执行');
      }
    },
    [findAgentRunIdByAction, findAgentSessionIdByAction, refreshAgentRunByAction, startChatAgentStream, upsertAgentSessionMessage],
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
    Modal.confirm({
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
      ? 'Workflow Run 路由中'
      : routingMode === 'chat'
        ? 'Chat'
        : 'Workflow Run';
  const activeModelLabel = useCloudAI
    ? selectedCloudModel || '未选择模型'
    : settings.modelId || '未选择模型';
  const agentOptions = primaryAgents.map((agent) => ({ value: agent.id, label: agent.name }));

  const agentFileSummaries = useMemo(() => {
    const seen = new Set<string>();
    const items: Array<{ id: string; path: string; status: string; summary: string; preview: string; depth: number }> = [];

    const depthOf = (path: string) => path.replace(/\\/g, '/').split('/').filter(Boolean).length;

    for (const message of messages) {
      const metadata = message.agent_metadata;
      if (!metadata || metadata.kind !== 'agent_part' || (metadata.agent_part as any)?.type !== 'diff') continue;
      const part: any = metadata.agent_part;
      const payload = part?.payload || {};
      const files = Array.isArray(payload.changed_files)
        ? payload.changed_files
        : Array.isArray(payload.files)
          ? payload.files.map((file: any) => file?.path || file?.file_path).filter(Boolean)
          : [];
      const diffSource = payload.diff || payload.payload?.diff || payload.file_changes || payload.payload?.file_changes;
      const diffText = typeof diffSource === 'string' ? diffSource : JSON.stringify(diffSource || payload, null, 2);
      const summary = part.title || part.content || payload.policy_reason || '文件变更';
      const fileEntries = Array.isArray(diffSource)
        ? diffSource
        : files.map((path: string) => ({ path, status: part.status || 'modified', summary, diff: diffText }));

      for (const entry of fileEntries) {
        const path = String(entry?.path || entry?.file_path || entry?.filename || entry?.name || '').trim();
        if (!path || seen.has(path)) continue;
        seen.add(path);
        items.push({
          id: `${metadata.agent_part_id || message.id}:${path}`,
          path,
          status: String(entry?.status || entry?.change_type || entry?.action || part.status || 'modified'),
          summary: String(entry?.summary || entry?.description || summary),
          preview: String(entry?.diff || entry?.patch || entry?.content || entry?.after || entry?.before || diffText),
          depth: depthOf(path),
        });
      }
    }

    return items.slice(-8).sort((a, b) => a.depth - b.depth || a.path.localeCompare(b.path));
  }, [messages]);

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
    const walk = (node: typeof agentFileTree, depth = 0) => {
      if (node.kind === 'folder' && node.path) folders.add(node.path);
      for (const child of node.children || []) walk(child, depth + 1);
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
      return (
        <div key={node.path} className={styles.agentFileCard} style={{ ['--file-depth' as any]: String(depth) }}>
          <div className={styles.agentFileTreeRow}>
            <div className={styles.agentFileTreeLine} aria-hidden="true">
              <span className={styles.agentFileTreeBranch} />
              <span className={styles.agentFileTreeDot} data-tone={statusTone} />
            </div>
            <div className={styles.agentFileCardBody}>
              <div className={styles.agentFileCardTop}>
                <div className={styles.agentFilePath}>{node.name}</div>
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
      workflowTemplateOptions={workflowTemplateOptions}
      selectedWorkflowTemplate={selectedWorkflowTemplate}
      onWorkflowTemplateChange={setSelectedWorkflowTemplate}
      creatingWorkflow={creatingWorkflow}
      isLoading={isLoading}
      isStreaming={isActivelyStreaming}
    />
  );

  const renderMessageItem = useCallback((index: number, msg: any) => (
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
      onApproveAgentStep={handleApproveAgentStep}
      onApproveAgentAction={handleApproveAgentAction}
      onRejectAgentAction={handleRejectAgentAction}
      onExecuteAgentAction={handleExecuteAgentAction}
      onRefreshAgentRun={handleRefreshAgentRun}
      onOpenAgentDetails={(url) => navigate(url)}
    />
  ), [
    isActivelyStreaming,
    messages.length,
    handleRetry,
    handleEditMessage,
    deleteMessage,
    handleApproveAgentStep,
    handleApproveAgentAction,
    handleRejectAgentAction,
    handleExecuteAgentAction,
    handleRefreshAgentRun,
    navigate,
  ]);

  const workflowHeader = (
    <motion.div
      initial={prefersReducedMotion ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : transitions.base}
      style={{
        marginBottom: 16,
        padding: '18px 20px',
        borderRadius: 20,
        border: '1px solid color-mix(in srgb, var(--border-color) 72%, transparent)',
        background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 96%, transparent), color-mix(in srgb, var(--bg-secondary) 92%, transparent))',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 6 }}>Workflow Run</div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>{workflowTitle}</h2>
          <div style={{ marginTop: 8, display: 'flex', gap: 10, flexWrap: 'wrap', color: 'var(--text-secondary)', fontSize: 13 }}>
            <span>Stage：{workflowSteps.length}</span>
            <span>Node：{workflowSteps.length > 0 ? workflowSteps[workflowSteps.length - 1]?.title || 'bootstrap' : 'bootstrap'}</span>
            <span>状态：{workflowStatus}</span>
            <span>模式：{routingMode === 'agent' ? 'Agent Task' : routingMode === 'auto' ? 'Workflow Run' : 'Chat'}</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Tag color="blue" style={{ borderRadius: 999, marginInlineEnd: 0 }}>Workflow Run</Tag>
          <Tag color="geekblue" style={{ borderRadius: 999, marginInlineEnd: 0 }}>{activeModeLabel}</Tag>
        </div>
      </div>
    </motion.div>
  );

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
        </div>
        <Tag color={agentFileSummaries.length ? 'processing' : 'default'} className={styles.agentFilePanelTag}>
          {agentFileSummaries.length ? `${agentFileSummaries.length} 个文件` : '暂无变更'}
        </Tag>
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
        theme={theme}
        onToggleTheme={toggleTheme}
        messageCount={messages.length}
        activeModeLabel={activeModeLabel}
        activeModelLabel={activeModelLabel}
      />
      <div className={styles.chatWorkspace}>
        <main className={styles.mainChatPane}>
          <div className={styles.workspaceSelectorBar}>
            <div className={styles.workspaceSelectorInfo}>
              <div className={styles.workspaceSelectorLabelRow}>
                <span className={styles.workspaceSelectorLabel}>本地工作区</span>
                <Tag color={selectedWorkspace ? 'green' : 'default'} className={styles.workspaceSelectorTag}>
                  {selectedWorkspace ? '已选中' : '未选择'}
                </Tag>
              </div>
              <span className={styles.workspaceSelectorHint}>选择已保存工作区，或直接填写项目根目录。</span>
              <span className={styles.workspaceSelectorMeta}>{selectedWorkspaceLabel}</span>
            </div>
            <div className={styles.workspaceSelectorControls}>
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                className={styles.workspaceSelect}
                placeholder="选择工作区"
                value={selectedWorkspaceId || undefined}
                options={availableWorkspaces.map((workspace) => ({
                  label: workspace.local_path ? `${workspace.name} · ${workspace.local_path}` : workspace.name,
                  value: workspace.id,
                }))}
                onChange={(value) => {
                  const nextId = value || '';
                  setSelectedWorkspaceId(nextId);
                  const selected = availableWorkspaces.find((workspace) => workspace.id === nextId);
                  if (selected?.local_path) {
                    setWorkspaceProjectPath(selected.local_path);
                  }
                  if (!nextId) {
                    setWorkspaceProjectPath('');
                  }
                }}
              />
              <Input
                className={styles.workspacePathInput}
                value={workspaceProjectPath}
                placeholder="例如：C:\\Projects\\my-app"
                onChange={(event) => setWorkspaceProjectPath(event.target.value)}
              />
            </div>
            <div className={styles.workspaceSelectorStatus}>
              <span className={styles.workspaceSelectorStatusText} data-tone={workspacePathStatus.tone}>
                {workspacePathStatus.text}
              </span>
            </div>
          </div>
          <motion.div
            {...sectionMotion}
            className={styles.chatMessagesArea}
            ref={scrollContainerRef}
            onScroll={enableVirtualScroll ? undefined : handleScroll}
          >
            <MotionList className={styles.messagesInner} stagger={0.04}>
              <MotionItem variant="scale">{workflowHeader}</MotionItem>
              {workflowSteps.length > 0 && (
                <MotionItem>
                  <div style={{ marginBottom: 18 }}>
                    {workflowStepCards}
                  </div>
                </MotionItem>
              )}
              {toolEvents.length > 0 && (
                <MotionItem>
                  <ToolEventTimeline events={toolEvents} />
                </MotionItem>
              )}
              {workflowSteps.length > 0 ? (
                <>
                  {messages.length > 0 && (
                    <MotionList stagger={0.03} style={{ marginTop: 10 }}>
                      {messages.map((msg, index) => (
                        <React.Fragment key={msg.id}>
                          {renderMessageItem(index, msg)}
                        </React.Fragment>
                      ))}
                    </MotionList>
                  )}
                  <MotionItem>
                    <AgentPhaseIndicator
                      phase={agentPhase.phase}
                      tool={agentPhase.tool}
                      visible={agentPhase.visible}
                    />
                  </MotionItem>
                  <div ref={messagesEndRef} style={{ height: 1 }} />
                </>
              ) : messages.length === 0 ? (
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
                    普通问题会停留在 Chat，开发任务会进入 Agent Task，多步骤编排则会进入 Workflow Run。
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
            onCreateWorkflow={handleCreateWorkflow}
            routingMode={routingMode}
            routing={routingIntent}
            autonomyMode={autonomyMode}
          />
        </main>

        {isDesktop && (
          <div className={styles.sidePanels}>
            <div className={styles.contextSidePanel}>{contextPanel}</div>
            <div className={styles.fileSidePanel}>{filePanel}</div>
          </div>
        )}
      </div>

      <Drawer
        title="对话设置"
        placement="right"
        width={360}
        open={!isDesktop && contextPanelOpen}
        onClose={() => setContextPanelOpen(false)}
        destroyOnClose={false}
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
          workflowTemplateOptions={workflowTemplateOptions}
          selectedWorkflowTemplate={selectedWorkflowTemplate}
          onWorkflowTemplateChange={setSelectedWorkflowTemplate}
          creatingWorkflow={creatingWorkflow}
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
