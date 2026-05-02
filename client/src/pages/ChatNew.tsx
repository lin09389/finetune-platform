import { Button, Modal } from 'antd';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';

import { useChatStream } from '../hooks/chat/useChatStream';
import { useResponsive } from '../hooks/useResponsive';
import { useShallow } from 'zustand/react/shallow';
import { useChatStore } from '../store/chatStore';
import { useTheme } from '../theme';

import ChatHeader from '../components/chat/ChatHeader';
import ChatInput from '../components/chat/ChatInput';
import FollowUpSuggestions from '../components/chat/FollowUpSuggestions';
import ChatHistoryDrawer from '../components/ChatHistoryDrawer';
import ChatMessage from '../components/ChatMessage';
import MemoryManager from '../components/MemoryManager';
import RuntimeContextPanel from '../components/runtime/RuntimeContextPanel';
import APIKeyManager from '../pages/APIKeyManager';

import { useRuntimeContext } from '../runtime/RuntimeContext';
import {
  API_BASE_URL,
  approveChatAgentAction,
  approveChatAgentStep,
  classifyChatAgentIntent,
  createChatAgentRun,
  executeChatAgentAction,
  getPrimaryAgents,
  getSavedCloudProviderData,
  getSavedCloudProviders,
  getWorkflowTemplates,
  getChatAgentRun,
  rejectChatAgentAction,
  runChatAgentRun,
} from '../services/api';
import type { AgentInfo, ChatAgentRun, SavedCloudProvider, WorkflowAction, WorkflowTemplate } from '../services/api';
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

const DEFAULT_SUGGESTIONS = [
  '帮我制定一个学习计划',
  '如何进行大模型微调？',
  '写一段 Python 代码实现数据清洗',
  '分析一下当前的 AI 行业趋势'
];

interface StoredChatScrollState {
  topIndex: number;
  atBottom: boolean;
  updatedAt: string;
}

const CHAT_SCROLL_STORAGE_KEY = 'chat_scroll_positions_v1';

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

const extractDynamicSuggestions = (content: string): string[] => {
  if (!content) return [];
  
  // 预处理：移除思考块 (thought blocks)
  const cleanContent = content.replace(/<thought>[\s\S]*?<\/thought>/g, '').trim();
  const lines = cleanContent.split('\n').map((l) => l.trim()).filter(Boolean);
  const suggestions: string[] = [];

  // 1. 寻找明确的建议引导语
  const suggestionMarkers = [
    '您可以尝试这样问',
    '您可以说',
    '例如',
    '可以问',
    '试着问',
    '你可以问',
    '后续建议',
    '猜你想问',
    'Next steps',
    'Follow-up'
  ];

  let markerFoundIndex = -1;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line && suggestionMarkers.some(marker => line.includes(marker))) {
      markerFoundIndex = i;
      break;
    }
  }

  // 如果找到了标记，尝试抓取其后的列表项
  if (markerFoundIndex !== -1) {
    for (let i = markerFoundIndex + 1; i < Math.min(markerFoundIndex + 6, lines.length); i++) {
      const line = lines[i];
      if (!line) continue;
      // 匹配列表项：- 项, * 项, 1. 项
      const listMatch = line.match(/^[*-]\s+(.+)$/) || line.match(/^\d+\.\s+(.+)$/);
      if (listMatch && listMatch[1]) {
        const s = listMatch[1].replace(/^["“]|["”]$/g, '').trim();
        if (s && s.length < 50) suggestions.push(s);
      }
    }
  }

  // 2. 如果没找到标记，尝试寻找末尾带有引号的列表项（常见的大模型输出习惯）
  if (suggestions.length === 0) {
    const lastLines = lines.slice(-8);
    for (const line of lastLines) {
      const quoteMatch = line.match(/^[*-]\s*["“]([^"”]+)["”]/) || line.match(/^\d+\.\s*["“]([^"”]+)["”]/);
      if (quoteMatch && quoteMatch[1]) {
        suggestions.push(quoteMatch[1].trim());
      }
    }
  }

  // 3. 兜底策略：如果内容末尾有问号，可能是一个建议
  if (suggestions.length === 0) {
    const lastLine = lines[lines.length - 1];
    if (lastLine && (lastLine.endsWith('?') || lastLine.endsWith('？')) && lastLine.length < 40) {
      suggestions.push(lastLine.replace(/^[*-]\s*/, '').trim());
    }
  }

  return Array.from(new Set(suggestions)).slice(0, 10);
};

const ChatPage: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const { isMobile } = useResponsive();
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

  const [useCloudAI, setUseCloudAI] = useState(false);
  const [cloudAIConfig, setCloudAIConfig] = useState<APIKeyConfig | null>(null);
  const [cloudProviders, setCloudProviders] = useState<SavedCloudProvider[]>([]);
  const [selectedCloudModel, setSelectedCloudModel] = useState<string>('');
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
  const chatAgentStreamsRef = useRef<Record<string, EventSource>>({});
  const refreshedAgentRunsRef = useRef<Set<string>>(new Set());
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
  const [isAtBottom, setIsAtBottom] = useState(shouldRestoreToBottom);
  const [showScrollButton, setShowScrollButton] = useState(false);

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
    if (virtuosoRef.current) {
      virtuosoRef.current.scrollToIndex({
        index: messages.length - 1,
        align: 'end',
        behavior: smooth ? 'smooth' : 'auto',
      });
      return;
    }
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto' });
    }
  }, [messages.length]);

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

  useEffect(() => {
    scrollToBottom(!isActivelyStreaming);
  }, [messages, isActivelyStreaming, scrollToBottom]);

  const loadCloudAIConfig = async () => {
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
    if (['不要执行', '只讨论', '只分析', '解释一下', '什么是'].some((keyword) => text.includes(keyword))) {
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
      '帮我改',
      '补丁',
      '执行',
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

  const persistAgentMessages = useCallback(async () => {
    const state = useChatStore.getState();
    if (!state.currentSessionId || state.currentSessionId.startsWith('local_')) return;
    await state.replaceCurrentSessionMessages(state.messages).catch(() => undefined);
  }, []);

  const upsertAgentMessages = useCallback(
    async (run: ChatAgentRun) => {
      if (!run.workflow_id) return;
      const state = useChatStore.getState();
      const current = state.messages;
      const existingRun = current.find(
        (message) => message.agent_metadata?.agent_run_id === run.id && message.agent_metadata.kind === 'agent_run_card',
      );
      const runContent = run.summary || `Agent 工作流状态：${run.status}`;
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

  useEffect(() => {
    if (!currentSessionId || currentSessionId.startsWith('local_') || messages.length === 0) return;
    const runIds = Array.from(
      new Set(
        messages
          .map((message) => message.agent_metadata?.agent_run_id)
          .filter((runId): runId is string => Boolean(runId)),
      ),
    );
    if (!runIds.length) return;

    let cancelled = false;
    runIds.forEach((runId) => {
      const refreshKey = `${currentSessionId}:${runId}`;
      if (refreshedAgentRunsRef.current.has(refreshKey)) return;
      refreshedAgentRunsRef.current.add(refreshKey);
      getChatAgentRun(runId)
        .then(async (run) => {
          if (!cancelled) {
            await upsertAgentMessages(run);
          }
        })
        .catch(() => {
          refreshedAgentRunsRef.current.delete(refreshKey);
        });
    });

    return () => {
      cancelled = true;
    };
  }, [currentSessionId, messages, upsertAgentMessages]);

  const handleAgentWorkflow = useCallback(
    async (
      content: string,
      forceAgent = false,
      options: { agentId?: string; templateId?: string; reason?: string } = {},
    ) => {
      const goal = content.trim();
      if (!goal) return false;
      if (!forceAgent && !isLikelyAgentGoal(goal)) return false;

      let sessionId = currentSessionId;
      if (!sessionId) {
        const session = await createSession();
        sessionId = session.id;
      }

      const userMessageId = addMessage({ role: 'user', content: goal });
      setCreatingWorkflow(true);
      try {
        const run = await createChatAgentRun({
          chat_session_id: sessionId && !sessionId.startsWith('local_') ? sessionId : undefined,
          message_id: userMessageId,
          content: goal,
          template_id: options.templateId || selectedWorkflowTemplate || 'software_delivery',
          provider: cloudAIConfig?.provider || undefined,
          model: selectedCloudModel || cloudAIConfig?.model || undefined,
          agent_id: options.agentId || selectedPrimaryAgent || 'build',
          autonomy_mode: autonomyMode,
          force_agent: forceAgent,
        });

        if (run.mode === 'chat') {
          useChatStore.setState((state) => ({
            messages: state.messages.filter((message) => message.id !== userMessageId),
          }));
          return false;
        }

        if (options.reason) {
          notify.info(options.reason);
        }
        await upsertAgentMessages(options.reason ? { ...run, summary: `${options.reason} ${run.summary || ''}` } : run);
        startChatAgentStream(run.id);
        const started = await runChatAgentRun(run.id);
        await upsertAgentMessages(started);
        notify.success('Agent 已开始工作');
        return true;
      } catch (error: any) {
        notify.error(error?.response?.data?.detail || 'Agent 工作启动失败');
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
      isLikelyAgentGoal,
      selectedCloudModel,
      selectedPrimaryAgent,
      selectedWorkflowTemplate,
      startChatAgentStream,
      upsertAgentMessages,
    ],
  );

  const handleSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      isAutoScrollEnabledRef.current = true;
      setTimeout(() => scrollToBottom(true, true), 100);

      if (routingMode === 'agent') {
        const handledByAgent = await handleAgentWorkflow(content, true, { reason: '已按 Agent 模式启动 Build Agent。' });
        if (handledByAgent) return;
      }

      if (routingMode === 'auto') {
        setRoutingIntent(true);
        try {
          const intent = await classifyChatAgentIntent({
            content,
            provider: cloudAIConfig?.provider || undefined,
            model: selectedCloudModel || cloudAIConfig?.model || undefined,
            agent_id: selectedPrimaryAgent || 'build',
            template_id: selectedWorkflowTemplate || 'software_delivery',
            chat_session_id: currentSessionId && !currentSessionId.startsWith('local_') ? currentSessionId : undefined,
            routing_mode: 'auto',
          });
          if (intent.mode === 'agent') {
            const handledByAgent = await handleAgentWorkflow(content, true, {
              agentId: intent.suggested_agent_id || selectedPrimaryAgent || 'build',
              templateId: intent.suggested_template_id || selectedWorkflowTemplate || 'software_delivery',
              reason: intent.source === 'cloud'
                ? `云端判断需要 Agent：${intent.reason}`
                : `已识别为开发任务，启动 Agent：${intent.reason}`,
            });
            if (handledByAgent) return;
          }
          if (intent.source === 'fallback') {
            notify.info(intent.reason);
          }
        } catch (error) {
          if (isLikelyAgentGoal(content)) {
            const handledByAgent = await handleAgentWorkflow(content, true, {
              reason: '意图判断失败，已按本地规则启动 Agent。',
            });
            if (handledByAgent) return;
          }
          notify.info('意图判断失败，已按普通对话处理。');
        } finally {
          setRoutingIntent(false);
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
        notify.warning('请先输入工作流目标');
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
      setCloudAIConfig((config) => {
        if (!config) return config;
        const nextConfig = { ...config, model };
        localStorage.setItem('cloud_ai_config', JSON.stringify(nextConfig));
        return nextConfig;
      });
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
      const run = await getChatAgentRun(runId);
      await upsertAgentMessages(run);
      if (run.recoverable && ['created', 'running', 'planning', 'implementing', 'reviewing'].includes(run.status)) {
        startChatAgentStream(run.id);
      }
    },
    [startChatAgentStream, upsertAgentMessages],
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
      const runId = findAgentRunIdByAction(actionId);
      if (runId) {
        startChatAgentStream(runId);
      }
      await approveChatAgentAction(actionId);
      await refreshAgentRunByAction(actionId);
    },
    [findAgentRunIdByAction, refreshAgentRunByAction, startChatAgentStream],
  );

  const handleRejectAgentAction = useCallback(
    async (actionId: string) => {
      await rejectChatAgentAction(actionId);
      await refreshAgentRunByAction(actionId);
    },
    [refreshAgentRunByAction],
  );

  const handleExecuteAgentAction = useCallback(
    async (actionId: string) => {
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
    [findAgentRunIdByAction, refreshAgentRunByAction, startChatAgentStream],
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

  const enableVirtualScroll = true;

  const currentSuggestions = React.useMemo(() => {
    if (messages.length === 0) return DEFAULT_SUGGESTIONS;
    if (isActivelyStreaming) return [];
    
    // 只有当最后一条消息是助手发出的，且没有正在加载时，才显示建议
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && lastMessage.role === 'assistant') {
      const extracted = extractDynamicSuggestions(lastMessage.content);
      
      // 更加智能的上下文启发式建议
      const content = lastMessage.content;
      const suggestions = new Set<string>(extracted);

      // 1. 如果包含代码块
      if (content.includes('```')) {
        suggestions.add('能帮我给这段代码加上详细注释吗？');
        suggestions.add('这段代码还有优化的空间吗？');
      }

      // 2. 如果包含步骤列表
      if (/^\d+\.\s/m.test(content) || /^-\s/m.test(content)) {
        suggestions.add('能详细展开其中的第一点吗？');
        suggestions.add('实际操作中这些步骤有哪些常见的坑？');
      }

      // 3. 如果包含报错或问题
      if (content.includes('错误') || content.includes('异常') || content.includes('error') || content.includes('Exception')) {
        suggestions.add('如何排查和解决这个错误？');
        suggestions.add('有其他可行的替代方案吗？');
      }

      // 4. 提取专业术语（简单匹配连续英文字符，如框架、库名）
      const termsMatch = content.match(/[A-Z][a-zA-Z]{2,}/g);
      if (termsMatch && termsMatch.length > 0) {
        // 过滤掉常见词汇，取第一个显著的词汇
        const ignoreList = ['The', 'This', 'That', 'How', 'What', 'When', 'And', 'For', 'With', 'But'];
        const validTerms = termsMatch.filter(t => !ignoreList.includes(t));
        if (validTerms.length > 0) {
          const term = validTerms[0];
          suggestions.add(`能深入讲解一下 ${term} 的底层原理吗？`);
        }
      }

      // 5. 补充兜底建议
      if (content.length > 200) {
        suggestions.add('总结一下核心观点');
        suggestions.add('这背后的核心原理是什么？');
        suggestions.add('请用更通俗的话解释一下');
      } else {
        suggestions.add('能再多举几个具体的例子吗？');
        suggestions.add('这有什么实际应用场景？');
      }
      
      // 如果建议太少，继续补充
      if (suggestions.size < 6) {
        suggestions.add('还有其他需要注意的细节吗？');
        suggestions.add('能对比一下其他类似的方案吗？');
        suggestions.add('有什么相关的最佳实践吗？');
      }

      return Array.from(suggestions);
    }
    
    return [];
  }, [messages, isActivelyStreaming]);

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

  return (
    <motion.div
      className={styles.chatContainer}
      initial={prefersReducedMotion ? false : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : transitions.slower}
      style={isMobile ? { height: 'calc(100vh - 64px)' } : undefined}
    >
      <ChatHeader
        onNewChat={() => createSession()}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenMemory={() => setMemoryManagerOpen(true)}
        onClearChat={handleClearChat}
        onExportChat={handleExportChat}
        currentBackend={settings.backend}
        backends={observed.inference.backends}
        onBackendChange={async (backend) => {
          setUseCloudAI(false);
          localStorage.setItem('chat_use_cloud_ai', '0');
          updateSettings({ backend: backend as 'ollama' | 'huggingface' | 'cloud', modelId: '' });
          setInferenceSelection({ backend, modelId: undefined });
          await refreshInference();
        }}
        currentModel={settings.modelId}
        models={modelOptions}
        onModelChange={(model) => {
          updateSettings({ modelId: model });
          setInferenceSelection({ backend: settings.backend, modelId: model });
        }}
        useCloudAI={useCloudAI}
        onToggleCloudAI={() => {
          if (!cloudAIConfig?.api_key && !cloudAIConfig?.key_id) {
            setConfigModalOpen(true);
          } else {
            setUseCloudAI(!useCloudAI);
          }
        }}
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
        onToggleMemory={() => updateSettings({ useMemory: !settings.useMemory })}
        theme={theme}
        onToggleTheme={toggleTheme}
        messageCount={messages.length}
        isLoading={isLoading}
        isStreaming={isActivelyStreaming}
      />
      <motion.div
        className={styles.chatMessagesArea}
        ref={scrollContainerRef}
        onScroll={enableVirtualScroll ? undefined : handleScroll}
        initial={prefersReducedMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={prefersReducedMotion ? { duration: 0 } : { delay: 0.16, ...transitions.base }}
      >
        <div className={styles.messagesInner}>
          <div style={{ marginBottom: 20 }}>
            <RuntimeContextPanel page="chat" />
          </div>
          {messages.length === 0 ? (
            <motion.div
              initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.94 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={prefersReducedMotion ? { duration: 0 } : transitions.spring}
              className={styles.emptyState}
            >
              <div className={styles.emptyOrb}>AI</div>
              <h3 className={styles.emptyTitle}>开始新的对话</h3>
              <p className={styles.emptyDesc}>选择模型后，输入你的问题并开始探索。</p>
              
              <div className={styles.starterSuggestions}>
                {DEFAULT_SUGGESTIONS.map((s, i) => (
                  <motion.button
                    key={s}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 + i * 0.1 }}
                    className={styles.starterBtn}
                    onClick={() => handleSend(s)}
                  >
                    {s}
                  </motion.button>
                ))}
              </div>
            </motion.div>
          ) : enableVirtualScroll ? (
            <Virtuoso
              key={currentSessionId || 'chat-empty'}
              ref={virtuosoRef}
              data={messages}
              itemContent={renderMessageItem}
              components={{
                Footer: () => (
                  <div style={{ paddingBottom: '20px' }}>
                    <FollowUpSuggestions
                      suggestions={currentSuggestions}
                      isVisible={!isLoading && !isActivelyStreaming && currentSuggestions.length > 0}
                      onSuggestionClick={handleSend}
                    />
                  </div>
                ),
              }}
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
                saveCurrentScrollState({ atBottom: nextIsAtBottom });
              }}
              followOutput={isAtBottom ? 'smooth' : false}
              style={{ height: '100%' }}
              alignToBottom
            />
          ) : (
            <>
              {messages.map((msg, index) => (
                <React.Fragment key={msg.id}>
                  {renderMessageItem(index, msg)}
                </React.Fragment>
              ))}
              
              <FollowUpSuggestions
                suggestions={currentSuggestions}
                isVisible={!isLoading && !isActivelyStreaming && currentSuggestions.length > 0}
                onSuggestionClick={handleSend}
              />

              <div ref={messagesEndRef} style={{ height: 1 }} />
            </>
          )}
        </div>
      </motion.div>

      <AnimatePresence>
        {showScrollButton && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            style={{
              position: 'absolute',
              bottom: isMobile ? 120 : 160,
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
        onStop={stopStream}
        onClear={handleClearChat}
        disabled={!settings.modelId && !useCloudAI}
        loading={isLoading}
        isStreaming={isActivelyStreaming}
        modelId={useCloudAI ? selectedCloudModel : settings.modelId}
        agentModeAvailable={primaryAgents.length > 0}
        onCreateWorkflow={handleCreateWorkflow}
        creatingWorkflow={creatingWorkflow}
        agentOptions={primaryAgents.map((agent) => ({ value: agent.id, label: agent.name }))}
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
      />

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
            void loadCloudAIConfig();
          }}
          initialConfig={cloudAIConfig}
        />
      </Modal>
    </motion.div>
  );
};

export default ChatPage;
