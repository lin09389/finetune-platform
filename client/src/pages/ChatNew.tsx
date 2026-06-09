import { Button, Drawer, Input, Modal, Tag, Tooltip } from 'antd';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';

import { useChatStream } from '../hooks/chat/useChatStream';
import { useAgentAsyncTasks } from '../hooks/chat/useAgentAsyncTasks';
import { useAgentWorkspace } from '../hooks/chat/useAgentWorkspace';
import { useAgentWorkspaceNextActionRouter } from '../hooks/chat/useAgentWorkspaceNextActionRouter';
import { useAgentWorkspaceSelection } from '../hooks/chat/useAgentWorkspaceSelection';
import { useResponsive } from '../hooks/useResponsive';
import { useOperation } from '../hooks/useOperation';
import { useShallow } from 'zustand/react/shallow';
import { useChatStore } from '../store/chatStore';
import { useAppStore } from '../store/appStore';
import { useTheme } from '../theme';
import { appModal } from '../utils/modal';

import ChatHeader from '../components/chat/ChatHeader';
import ChatContextPanel from '../components/chat/ChatContextPanel';
import ChatInput from '../components/chat/ChatInput';
import HitlApprovalPanel from '../components/chat/HitlApprovalPanel';
import AgentPhaseIndicator from '../components/chat/AgentPhaseIndicator';
import { WorkbenchEmpty } from '../components/chat/AgentWorkbenchPanel';
import AgentWorkspaceStatusBar from '../components/chat/AgentWorkspaceStatusBar';
import AgentWorkspaceContainer from '../components/chat/AgentWorkspaceContainer';
import AgentWorkspaceEditor from '../components/chat/AgentWorkspaceEditor';
import AgentTerminal from '../components/chat/AgentTerminal';
import QuickFileOpener, { flattenFileNodes } from '../components/chat/QuickFileOpener';
import { getFileIcon, isTextIcon } from '../utils/fileIcons';
import { parseDiffHunks } from '../utils/diffHunks';
import type { OpenedFile } from '../components/chat/AgentWorkspaceEditor';
import ChatHistoryDrawer from '../components/ChatHistoryDrawer';
import ChatMessage from '../components/ChatMessage';
import MemoryManager from '../components/MemoryManager';
import APIKeyManager from '../pages/APIKeyManager';
import { getAgentSessionUiState } from '../hooks/chat/useAgentSessionViewModel';
import { buildAgentSessionStreamUrl, getAgentStreamRetryDelay } from '../utils/agentSessionStream';

import { useRuntimeContext } from '../runtime/RuntimeContext';
import {
  classifyChatAgentIntent,
  createAgentSession,
  decideAgentPermission,
  extractApiErrorMessage,
  getArtifactOriginal,
  getAgentSession,
  getAgentSessionOverview,
  getAgentSkills,
  getPrimaryAgents,
  getSavedCloudProviderData,
  getSavedCloudProviders,
  interruptAgentSession,
  listWorkspaces,
  browseFolderBackend,
  getWorkspaceTree,
  readWorkspaceFile,
  writeWorkspaceFile,
  promptAgentSession,
} from '../services/api';
import type { ActiveFileContext, AgentArtifact, AgentHitlDecision, AgentInfo, AgentPart, AgentSession, AgentSessionEvent, AgentSessionOverview, AgentSkillSource, ExplicitContextMention, SavedCloudProvider, WorkspaceSummary, WorkspaceTreeNode } from '../services/api';
import { transitions } from '../theme/animations';
import { notify } from '../utils/notify';
import { ArrowDownOutlined, FolderOpenOutlined } from '@ant-design/icons';
import styles from './ChatNew.module.css';

interface APIKeyConfig {
  provider: string;
  api_key?: string;
  key_id?: string;
  model?: string;
  group_id?: string;
  base_url?: string;
}

const AGENT_MODEL_PROVIDER_ALIASES: Record<string, string> = {
  anthropic: 'anthropic',
  baseten: 'baseten',
  deepseek: 'deepseek',
  fireworks: 'fireworks',
  'google-genai': 'google_genai',
  google_genai: 'google_genai',
  'google-vertexai': 'google_vertexai',
  google_vertexai: 'google_vertexai',
  ollama: 'ollama',
  openai: 'openai',
  openrouter: 'openrouter',
};

type AgentStreamRetryState = {
  attempt: number;
  timer: ReturnType<typeof setTimeout> | null;
  lastEventId: string;
};

function resolveAgentModelConfig(params: {
  useCloudAI: boolean;
  cloudConfig: APIKeyConfig | null;
  selectedCloudModel?: string;
  localBackend?: string;
  localModel?: string;
}): { provider: string; model: string } {
  const rawProvider = (params.useCloudAI ? params.cloudConfig?.provider || '' : params.localBackend || '').trim();
  const rawModel = (params.useCloudAI ? params.selectedCloudModel || params.cloudConfig?.model || '' : params.localModel || '').trim();
  if (!rawModel) {
    throw new Error('Agent 需要先选择一个支持工具调用的模型。');
  }
  const colonIndex = rawModel.indexOf(':');
  if (colonIndex > 0) {
    const prefix = rawModel.slice(0, colonIndex);
    const model = rawModel.slice(colonIndex + 1);
    const provider = AGENT_MODEL_PROVIDER_ALIASES[prefix];
    if (provider && model) {
      return { provider, model };
    }
  }
  const provider = AGENT_MODEL_PROVIDER_ALIASES[rawProvider];
  if (!provider) {
    throw new Error(`Agent 现在只支持官方 DeepAgents 模型 provider:model。当前服务商 ${rawProvider || '未选择'} 不能用于 Agent。`);
  }
  return { provider, model: rawModel };
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
  transition: { duration: 0.26, ease: [0.23, 1, 0.32, 1] as const },
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
const CHAT_PANE_WIDTH_STORAGE_KEY = 'chat_chat_pane_width_v1';
const CHAT_SIDE_PANEL_OPEN_STORAGE_KEY = 'chat_side_panel_open_v1';
const CHAT_PANEL_OPEN_STORAGE_KEY = 'chat_chat_panel_open_v1';
const CHAT_AGENT_SKILL_SOURCES_STORAGE_KEY = 'chat_agent_skill_sources_v1';

const resolveArtifactStatus = (statusRaw: string): OpenedFile['status'] => {
  const s = statusRaw.toLowerCase();
  if (/add|new|create|新增/.test(s)) return 'added';
  if (/delete|remove|removed|删除/.test(s)) return 'deleted';
  if (/modify|update|change|edit|fix|modified|修改/.test(s)) return 'modified';
  return 'unknown';
};

const getChangedFilesFromPayload = (payload?: Record<string, any>) => {
  const files = payload?.changed_files || payload?.payload?.changed_files || payload?.files || payload?.payload?.files || [];
  if (!Array.isArray(files)) return [];
  return files.map((item: any) => (typeof item === 'string' ? item : item?.path || item?.file_path)).filter(Boolean) as string[];
};


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
  const operation = useOperation();
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
  const [agentSkillSources, setAgentSkillSources] = useState<AgentSkillSource[]>([]);
  const [selectedSkillSources, setSelectedSkillSources] = useState<string[]>(() => {
    try {
      const parsed = JSON.parse(localStorage.getItem(CHAT_AGENT_SKILL_SOURCES_STORAGE_KEY) || 'null');
      return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string') : [];
    } catch {
      return [];
    }
  });
  const [skillsInitialized, setSkillsInitialized] = useState(() => localStorage.getItem(CHAT_AGENT_SKILL_SOURCES_STORAGE_KEY) !== null);
  const [skillsLoading, setSkillsLoading] = useState(false);
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
  const [agentSessionOverview, setAgentSessionOverview] = useState<AgentSessionOverview | null>(null);
  const [workbenchActiveTab, setWorkbenchActiveTab] = useState('execution');
  const agentSessionStreamsRef = useRef<Record<string, EventSource>>({});
  const agentSessionStreamRetryRef = useRef<Record<string, AgentStreamRetryState>>({});
  const startAgentSessionStreamRef = useRef<((sessionId: string, fromRetry?: boolean) => void) | null>(null);
  const agentSessionStateRef = useRef<Record<string, AgentSession>>({});
  const agentWorkspaceRefreshRef = useRef<(() => Promise<void>) | null>(null);
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
  const [chatPaneWidth, setChatPaneWidth] = useState(() => {
    if (typeof window === 'undefined') return 380;
    const stored = Number(localStorage.getItem(CHAT_PANE_WIDTH_STORAGE_KEY));
    return Number.isFinite(stored) && stored >= 240 ? stored : 380;
  });
  const [resizingChatPane, setResizingChatPane] = useState(false);
  const [sidePanelOpen, setSidePanelOpen] = useState(() => {
    if (typeof window === 'undefined') return true;
    return localStorage.getItem(CHAT_SIDE_PANEL_OPEN_STORAGE_KEY) !== '0';
  });
  const [chatPanelOpen, setChatPanelOpen] = useState(() => {
    if (typeof window === 'undefined') return true;
    return localStorage.getItem(CHAT_PANEL_OPEN_STORAGE_KEY) !== '0';
  });
  const [showPathEdit, setShowPathEdit] = useState(false);
  const [openedFiles, setOpenedFiles] = useState<OpenedFile[]>([]);
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null);
  const lastAutoOpenedPartIdRef = useRef<string | null>(null);
  const activeFileContext = useAppStore((state) => state.activeFileContext);
  const setActiveFileContext = useAppStore((state) => state.setActiveFileContext);
  const [explicitContextMentions, setExplicitContextMentions] = useState<ExplicitContextMention[]>([]);

  // ── Dual-mode file tree: 'agent' = Agent's changed files, 'workspace' = full file tree ──
  const [fileTreeMode, setFileTreeMode] = useState<'agent' | 'workspace'>('agent');
  const [workspaceTreeNodes, setWorkspaceTreeNodes] = useState<WorkspaceTreeNode[]>([]);
  const [workspaceTreeRoot, setWorkspaceTreeRoot] = useState<string>('');
  const [workspaceTreeLoading, setWorkspaceTreeLoading] = useState(false);
  const [wsExpandedFolders, setWsExpandedFolders] = useState<Set<string>>(new Set());
  const workspaceFileNodes = useMemo(() => flattenFileNodes(workspaceTreeNodes), [workspaceTreeNodes]);

  // ── Integrated terminal dock ──────────────────────────────────────────────────
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [activeTerminalId, setActiveTerminalId] = useState<string | null>(null);
  const [terminalHeight, setTerminalHeight] = useState(() => {
    if (typeof window === 'undefined') return 240;
    const stored = Number(localStorage.getItem('terminal_dock_height'));
    return Number.isFinite(stored) && stored >= 120 ? stored : 240;
  });
  const [resizingTerminal, setResizingTerminal] = useState(false);

  // ── Ctrl+P Quick File Opener ──────────────────────────────────────────────────
  const [quickOpenVisible, setQuickOpenVisible] = useState(false);
  const [recentPaths, setRecentPaths] = useState<string[]>([]);

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
    if (settings.projectPath !== effectiveProjectPath) {
      updateSettings({ projectPath: effectiveProjectPath });
    }
  }, [effectiveProjectPath, settings.projectPath, updateSettings]);

  const loadAgentSkills = useCallback(async () => {
    setSkillsLoading(true);
    try {
      const registry = await getAgentSkills({
        project_path: effectiveProjectPath || undefined,
        agent_id: selectedPrimaryAgent || 'build',
      });
      const sources = registry.sources || [];
      setAgentSkillSources(sources);
      setSelectedSkillSources((current) => {
        const available = new Set(sources.filter((source) => source.available).map((source) => source.virtual_path));
        if (!skillsInitialized) {
          return sources
            .filter((source) => source.available && source.enabled_by_default)
            .map((source) => source.virtual_path);
        }
        return current.filter((source) => available.has(source));
      });
      setSkillsInitialized(true);
    } catch {
      setAgentSkillSources([]);
    } finally {
      setSkillsLoading(false);
    }
  }, [effectiveProjectPath, selectedPrimaryAgent, skillsInitialized]);

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
    const resizingColClass = styles.resizing;
    const resizingRowClass = 'resizingTerminal';
    if (resizingColClass) {
      document.body.classList.toggle(resizingColClass, resizingSidePanel || resizingChatPane);
    }
    document.body.classList.toggle(resizingRowClass, resizingTerminal);
    return () => {
      if (resizingColClass) document.body.classList.remove(resizingColClass);
      document.body.classList.remove(resizingRowClass);
    };
  }, [resizingSidePanel, resizingChatPane, resizingTerminal]);

  const handleSplitterPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidePanelWidth;
    const minSideWidth = 280;
    const maxSideWidth = Math.max(320, window.innerWidth - 520);
    setResizingSidePanel(true);
    let pendingX = startX;
    let rafId: number | null = null;

    const handlePointerMove = (moveEvent: PointerEvent) => {
      pendingX = moveEvent.clientX;
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setSidePanelWidth(Math.min(maxSideWidth, Math.max(minSideWidth, startWidth - (pendingX - startX))));
      });
    };

    const handlePointerUp = () => {
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
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

  useEffect(() => {
    localStorage.setItem(CHAT_PANE_WIDTH_STORAGE_KEY, String(chatPaneWidth));
  }, [chatPaneWidth]);

  useEffect(() => {
    localStorage.setItem(CHAT_SIDE_PANEL_OPEN_STORAGE_KEY, sidePanelOpen ? '1' : '0');
  }, [sidePanelOpen]);

  useEffect(() => {
    localStorage.setItem(CHAT_PANEL_OPEN_STORAGE_KEY, chatPanelOpen ? '1' : '0');
  }, [chatPanelOpen]);

  const handleChatSplitterPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = chatPaneWidth;
    const minChatWidth = 240;
    const maxChatWidth = Math.max(280, window.innerWidth - 720);
    setResizingChatPane(true);
    let pendingX = startX;
    let rafId: number | null = null;

    const handlePointerMove = (moveEvent: PointerEvent) => {
      pendingX = moveEvent.clientX;
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setChatPaneWidth(Math.min(maxChatWidth, Math.max(minChatWidth, startWidth + (pendingX - startX))));
      });
    };

    const handlePointerUp = () => {
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
      setResizingChatPane(false);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  }, [chatPaneWidth]);

  useEffect(() => {
    localStorage.setItem('terminal_dock_height', String(terminalHeight));
  }, [terminalHeight]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault();
        setQuickOpenVisible(true);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleTerminalSplitterPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = terminalHeight;
    const minHeight = 120;
    const maxHeight = Math.max(180, window.innerHeight * 0.6);
    setResizingTerminal(true);
    let pendingY = startY;
    let rafId: number | null = null;

    const handlePointerMove = (moveEvent: PointerEvent) => {
      pendingY = moveEvent.clientY;
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setTerminalHeight(Math.min(maxHeight, Math.max(minHeight, startHeight - (pendingY - startY))));
      });
    };

    const handlePointerUp = () => {
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
      setResizingTerminal(false);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  }, [terminalHeight]);

  const handleBreadcrumbClick = useCallback((_segment: string, fullPath: string) => {
    setFileTreeMode('workspace');
    let relPath = fullPath;
    const root = workspaceTreeRoot.replace(/\\/g, '/');
    if (relPath.startsWith(root)) {
      relPath = relPath.slice(root.length).replace(/^\//, '');
    }
    const parts = relPath.split('/').filter(Boolean);
    setWsExpandedFolders((prev) => {
      const next = new Set(prev);
      let cumulative = '';
      for (const p of parts) {
        cumulative = cumulative ? `${cumulative}/${p}` : p;
        next.add(cumulative);
      }
      return next;
    });
  }, [workspaceTreeRoot]);

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
    const stoppableStatuses = new Set(['running', 'verifying', 'repairing']);
    return Array.from(
      new Set(
        messages
          .filter((message) => {
            const metadata = message.agent_metadata;
            return Boolean(
              metadata?.agent_session_id &&
              (stoppableStatuses.has(metadata.status || '') || (message.isLoading && metadata.status !== 'waiting_approval' && metadata.status !== 'waiting_permission')),
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
      loadAgentSkills(),
      refreshKnowledge(),
    ]).then((results) => {
      const failed = results.filter((r) => r.status === 'rejected');
      if (failed.length > 0) {
        console.warn(`${failed.length} init requests failed`);
      }
    });
  }, [loadAgentSkills, loadSessions, refreshInference, refreshKnowledge]);

  useEffect(() => () => {
    if (autoScrollFrameRef.current !== null) cancelAnimationFrame(autoScrollFrameRef.current);
    Object.values(agentSessionStreamsRef.current).forEach((source) => source.close());
    Object.values(agentSessionStreamRetryRef.current).forEach((retryState) => {
      if (retryState.timer) clearTimeout(retryState.timer);
    });
    agentSessionStreamsRef.current = {};
    agentSessionStreamRetryRef.current = {};
  }, []);

  useEffect(() => {
    localStorage.setItem('chat_primary_agent', selectedPrimaryAgent);
  }, [selectedPrimaryAgent]);

  useEffect(() => {
    if (!skillsInitialized) return;
    localStorage.setItem(CHAT_AGENT_SKILL_SOURCES_STORAGE_KEY, JSON.stringify(selectedSkillSources));
  }, [selectedSkillSources, skillsInitialized]);

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
    void loadAgentSkills();
  }, [loadAgentSkills]);

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

        const defaultWorkspace = workspaces.find((w) => w.status === 'default' && w.local_path) || workspaces.find((w) => w.local_path);

        setSelectedWorkspaceId((currentId) => {
          if (!currentId && defaultWorkspace?.id) return defaultWorkspace.id;
          return currentId;
        });

        setWorkspaceProjectPath((currentPath) => {
          if (!currentPath.trim() && defaultWorkspace?.local_path) return defaultWorkspace.local_path;
          return currentPath;
        });

      } catch {
        if (!cancelled) setAvailableWorkspaces([]);
      }
    };
    void loadWorkspaceOptions();
    return () => {
      cancelled = true;
    };
  }, []);

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
    if ([
      '不要执行', '只讨论', '只分析', '解释一下', '帮我解释', '什么是', '为什么',
      '怎么理解', '怎么用', '是什么意思', '有什么区别', '介绍一下', '帮我看看',
      '分析一下', '看看代码', '这个代码', '这段代码', '看看逻辑', '怎么实现的',
      '原理是什么', '怎么工作的', '帮我梳理', '帮我看看代码',
      '示例', '例子', 'demo', '演示', 'sample', '怎么写', '如何写',
    ].some((keyword) => text.includes(keyword))) {
      return false;
    }
    return [
      '修改代码', '新增功能', '新增接口', '新增页面',
      '实现功能', '实现接口', '修复bug', '修复报错',
      '重构代码', '优化代码',
      '跑测试', '运行测试', 'typecheck', 'pytest', 'npm run',
      '让agent做', '自动处理', '生成补丁', '写补丁',
      '搜索项目', '写脚本', '排查报错', '排查问题',
      '运行命令', '执行补丁',
      '帮我改', '帮我修', '帮我写', '帮我实现',
      '帮我新增', '帮我添加', '帮我重构',
      '改成', '改为', '加个', '加一个',
    ].some((keyword) => text.includes(keyword));
  }, []);

  const isReadOnlyProjectDiscussion = useCallback((content: string) => {
    const text = content.trim().toLowerCase();
    if (!text) return false;
    const actionKeywords = [
      '修改', '改代码', '新增', '添加', '实现', '修复', '重构', '优化代码',
      '跑测试', '运行测试', '执行', '运行命令', '安装', '写入', '编辑',
      '生成补丁', '写补丁', 'apply patch', 'pytest', 'npm run', 'typecheck',
    ];
    if (actionKeywords.some((keyword) => text.includes(keyword))) {
      return false;
    }
    const projectKeywords = [
      '这个项目', '当前项目', '项目结构', '项目代码', '项目里',
      '检查一下', '检查下', '看一下项目', '看看项目', '分析一下项目',
      '分析项目', '梳理项目', '理解项目', '项目问题', '深度问题',
    ];
    return projectKeywords.some((keyword) => text.includes(keyword));
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
    const uiState = getAgentSessionUiState(session);
    const uiItem = uiState.timeline.find((item) => item.part_id === part.id || item.id === part.id);
    const actionLike = part.type === 'permission' && uiState.pending_permission?.part_id === part.id;
    const summaryPart = part.type === 'summary' ? part : [...(session.parts || [])].reverse().find((item) => item.type === 'summary');
    return {
      agent_run_id: session.id,
      agent_session_id: session.id,
      agent_part_id: part.id,
      kind: 'agent_part' as const,
      status: part.status || session.status,
      action_id: actionLike ? part.id : undefined,
      action_type: part.type,
      can_approve: actionLike && part.status === 'pending',
      can_execute: false,
      ui_state: uiState,
      ui_item: uiItem,
      active_agent_id: session.agent_id,
      task_plan: session.metadata?.task_plan,
      current_stage_id: session.metadata?.current_stage_id,
      current_node_id: session.metadata?.current_node_id,
      agent_part: part,
      agent_parts: session.parts,
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

  const scheduleAgentSessionRefresh = useCallback(
    (sessionId: string, delays = [1000, 3000, 6000]) => {
      delays.forEach((delay) => {
        window.setTimeout(() => {
          getAgentSession(sessionId)
            .then((session) => upsertAgentSessionMessage(session))
            .catch(() => undefined);
        }, delay);
      });
    },
    [upsertAgentSessionMessage],
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

  const callbacksRef = useRef({
    ensureAgentSessionSnapshot,
    upsertAgentSessionMessage,
    upsertAgentSessionPartMessage,
    appendAgentSessionError,
  });
  useEffect(() => {
    callbacksRef.current = {
      ensureAgentSessionSnapshot,
      upsertAgentSessionMessage,
      upsertAgentSessionPartMessage,
      appendAgentSessionError,
    };
  }, [ensureAgentSessionSnapshot, upsertAgentSessionMessage, upsertAgentSessionPartMessage, appendAgentSessionError]);

  const clearAgentSessionRetry = useCallback((sessionId: string) => {
    const retryState = agentSessionStreamRetryRef.current[sessionId];
    if (retryState?.timer) {
      clearTimeout(retryState.timer);
      retryState.timer = null;
    }
  }, []);

  const closeAgentSessionStream = useCallback((sessionId: string, clearRetry = true) => {
    agentSessionStreamsRef.current[sessionId]?.close();
    delete agentSessionStreamsRef.current[sessionId];
    if (clearRetry) {
      clearAgentSessionRetry(sessionId);
      delete agentSessionStreamRetryRef.current[sessionId];
    }
  }, [clearAgentSessionRetry]);

  const startAgentSessionStream = useCallback(
    (sessionId: string, fromRetry = false) => {
      closeAgentSessionStream(sessionId, false);
      const retryState = agentSessionStreamRetryRef.current[sessionId] || { attempt: 0, timer: null, lastEventId: '' };
      retryState.timer = null;
      if (!fromRetry) retryState.attempt = 0;
      agentSessionStreamRetryRef.current[sessionId] = retryState;
      const source = new EventSource(buildAgentSessionStreamUrl(sessionId, retryState.lastEventId));
      console.log('[Agent] EventSource connected:', sessionId);
      agentSessionStreamsRef.current[sessionId] = source;
      const markStreamHealthy = () => {
        retryState.attempt = 0;
        setAgentPhase((prev) => prev.phase === 'connection_lost' ? { phase: '', visible: false } : prev);
      };
      const handleChunk = async (chunk: AgentSessionEvent) => {
        if (typeof chunk.id === 'string' && chunk.id) {
          retryState.lastEventId = chunk.id;
        }
        markStreamHealthy();
        const part = chunk.part || undefined;
        const sessionStatus = chunk.session_status;
        const agentId = chunk.agent_id;

        if (chunk.chunk_type === 'session_snapshot') {
          const snapshot = chunk.session_snapshot;
          if (snapshot) {
            await callbacksRef.current.upsertAgentSessionMessage(snapshot as AgentSession);
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

          const isTerminal = ['completed', 'failed', 'needs_manual_review', 'interrupted'].includes(sessionStatus || '');
          if (isTerminal) {
            closeAgentSessionStream(sessionId);
            Object.keys(streamingDeltaRef.current).forEach((key) => {
              if (key.startsWith('agp_')) delete streamingDeltaRef.current[key];
            });
            setAgentPhase({ phase: '', visible: false });
          }
          return;
        }

        if (sessionStatus || agentId) {
          callbacksRef.current.ensureAgentSessionSnapshot(sessionId, {
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
        if (['part_complete', 'part_snapshot', 'status', 'summary', 'error', 'async_task', 'done'].includes(String(chunk.chunk_type || ''))) {
          void agentWorkspaceRefreshRef.current?.();
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
            await callbacksRef.current.upsertAgentSessionPartMessage(
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

        const shouldRefreshSnapshot =
          chunk.chunk_type === 'action' || sessionStatus === 'waiting_approval' || sessionStatus === 'waiting_permission';
        if (shouldRefreshSnapshot) {
          getAgentSession(sessionId)
            .then((session) => callbacksRef.current.upsertAgentSessionMessage(session))
            .catch(() => undefined);
        }
      };
      source.addEventListener('agent_session_event', (e: MessageEvent) => {
        try { void handleChunk(JSON.parse((e as MessageEvent).data) as AgentSessionEvent); } catch { /* ignore */ }
      });
      source.addEventListener('agent_session_done', () => {
        useChatStore.getState().flushMessageUpdates();
        getAgentSession(sessionId)
          .then((session) => {
            callbacksRef.current.upsertAgentSessionMessage(session);
            if (!session.parts?.length && ['running', 'verifying', 'repairing'].includes(session.status)) {
              callbacksRef.current.appendAgentSessionError('Agent 事件流已中断，后端可能仍在运行旧代码或连接被服务端关闭。请重启后端后重试。', session);
            }
            setAgentPhase({ phase: '', visible: false });
          })
          .catch(() => undefined);
        closeAgentSessionStream(sessionId);
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
            callbacksRef.current.upsertAgentSessionMessage(session);
            if (['completed', 'failed', 'needs_manual_review', 'interrupted'].includes(session.status)) {
              closeAgentSessionStream(sessionId);
              setAgentPhase({ phase: '', visible: false });
            }
          })
          .catch(() => {
            console.warn('[Agent] Failed to refresh session after stream error:', sessionId);
          });
        closeAgentSessionStream(sessionId, false);
        if (!retryState.timer) {
          const delay = getAgentStreamRetryDelay(retryState.attempt);
          retryState.attempt += 1;
          retryState.timer = setTimeout(() => {
            retryState.timer = null;
            startAgentSessionStreamRef.current?.(sessionId, true);
          }, delay);
        }
      };
    },
    [closeAgentSessionStream],
  );

  useEffect(() => {
    startAgentSessionStreamRef.current = startAgentSessionStream;
  }, [startAgentSessionStream]);

  useEffect(() => {
    if (!currentSessionId || currentSessionId.startsWith('local_')) {
      Object.keys(agentSessionStreamsRef.current).forEach((sessionId) => closeAgentSessionStream(sessionId));
      return;
    }
    const agentSessionIds = Array.from(
      new Set(
        messages
          .map((message) => message.agent_metadata?.agent_session_id)
          .filter((sessionId): sessionId is string => Boolean(sessionId)),
      ),
    );

    // Close streams that are no longer in the active messages list
    const activeIdsSet = new Set(agentSessionIds);
    Object.keys(agentSessionStreamsRef.current).forEach((sessionId) => {
      if (!activeIdsSet.has(sessionId)) {
        closeAgentSessionStream(sessionId);
      }
    });
    Object.keys(agentSessionStreamRetryRef.current).forEach((sessionId) => {
      if (!activeIdsSet.has(sessionId)) {
        closeAgentSessionStream(sessionId);
      }
    });

    if (!agentSessionIds.length) return;

    agentSessionIds.forEach((sessionId) => {
      if (!agentSessionStreamsRef.current[sessionId]) {
        startAgentSessionStream(sessionId);
      }
    });

  }, [currentSessionId, messages, startAgentSessionStream, closeAgentSessionStream]);

  const buildDeepContextPayload = useCallback(() => ({
    active_context: activeFileContext,
    explicit_context: explicitContextMentions,
  }), [activeFileContext, explicitContextMentions]);

  const handleActiveEditorContextChange = useCallback((context: ActiveFileContext | null) => {
    setActiveFileContext(context);
  }, [setActiveFileContext]);

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
        const agentModel = resolveAgentModelConfig({
          useCloudAI,
          cloudConfig: cloudAIConfig,
          selectedCloudModel,
          localBackend: settings.backend,
          localModel: settings.modelId,
        });
        const workspaceContext = selectedWorkspaceLabel !== '未选择工作区'
          ? ` · ${selectedWorkspaceLabel}`
          : '';
        const session = await withTimeout(
          createAgentSession({
            chat_session_id: sessionId && !sessionId.startsWith('local_') ? sessionId : undefined,
            agent_id: options?.agentId || selectedPrimaryAgent || 'build',
            title:
              options.mode === 'agent'
                ? `${goal.slice(0, 26) || 'Agent Task'}${workspaceContext}`.slice(0, 64)
                : '',
            project_path: effectiveProjectPath || undefined,
            provider: agentModel.provider,
            model: agentModel.model,
            autonomy_mode: autonomyMode,
            enabled_skill_sources: skillsInitialized ? selectedSkillSources : null,
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
            provider: agentModel.provider,
            model: agentModel.model,
            ...buildDeepContextPayload(),
          }),
          15000,
          'prompt_session_timeout',
        );
        await upsertAgentSessionMessage(started);
        scheduleAgentSessionRefresh(session.id);
        return true;
      } catch (error: any) {
        const isTimeout = error?.message === 'create_session_timeout' || error?.message === 'prompt_session_timeout';
        const detail = isTimeout ? '服务器响应超时，请稍后重试' : extractApiErrorMessage(error, 'Agent 工作启动失败');
        const fallback = `Agent 工作启动失败：${detail}`;
        notify.error(fallback);
        await appendAgentSessionError(fallback, agentSession || {
          id: sessionId ? `agent_error_${sessionId}_${Date.now()}` : undefined,
          chat_session_id: sessionId && !sessionId.startsWith('local_') ? sessionId : undefined,
          agent_id: options?.agentId || selectedPrimaryAgent || 'build',
          title: `${goal.slice(0, 26) || 'Agent Session'}${selectedWorkspaceLabel !== '未选择工作区' ? ` · ${selectedWorkspaceLabel}` : ''}`.slice(0, 64),
          provider: undefined,
          model: undefined,
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
      buildDeepContextPayload,
      cloudAIConfig?.model,
      cloudAIConfig?.provider,
      createSession,
      currentSessionId,
      appendAgentSessionError,
      isLikelyAgentGoal,
      effectiveProjectPath,
      selectedCloudModel,
      selectedPrimaryAgent,
      selectedSkillSources,
      selectedWorkspaceLabel,
      skillsInitialized,
      scheduleAgentSessionRefresh,
      startAgentSessionStream,
      settings.backend,
      settings.modelId,
      upsertAgentSessionMessage,
      useCloudAI,
    ],
  );

  const handleSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      isAutoScrollEnabledRef.current = true;
      setTimeout(() => scrollToBottom(true, true), 100);

      let tempUserId: string | undefined;
      let tempLoadingId: string | undefined;
      const readOnlyProjectDiscussion = isReadOnlyProjectDiscussion(content);
      const shouldPreferAgent = routingMode === 'agent' || (routingMode === 'auto' && !readOnlyProjectDiscussion);

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
                ...buildDeepContextPayload(),
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
        const effectiveCloudModel = selectedCloudModel || cloudAIConfig.model || '';
        await sendCloudMessage(
          { prompt: content, deepContext: buildDeepContextPayload() },
          {
            provider: cloudAIConfig.provider,
            apiKey: cloudAIConfig.api_key,
            keyId: cloudAIConfig.key_id,
            model: effectiveCloudModel,
            groupId: cloudAIConfig.group_id,
            baseUrl: cloudAIConfig.base_url,
          },
        );
      } else {
        await sendMessage({ prompt: content, deepContext: buildDeepContextPayload() });
      }
    },
    [
      addMessage,
      cloudAIConfig,
      buildDeepContextPayload,
      currentSessionId,
      deleteMessage,
      handleAgentSession,
      isLikelyAgentGoal,
      isReadOnlyProjectDiscussion,
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

    await operation.run(async () => {
      await Promise.all(
        activeAgentSessionIds.map(async (sessionId) => {
          const session = await interruptAgentSession(sessionId);
          agentSessionStreamsRef.current[sessionId]?.close();
          delete agentSessionStreamsRef.current[sessionId];
          await upsertAgentSessionMessage(session);
        }),
      );
      setAgentPhase({ phase: '', visible: false });
    }, {
      key: 'stop-agent-runs',
      loadingText: '正在中断 Agent 任务...',
      successText: '已中断 Agent 任务',
      errorText: '中断 Agent',
    });
  }, [activeAgentSessionIds, operation, stopStream, upsertAgentSessionMessage]);

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

  const pendingApproval = useMemo(() => {
    return [...messages]
      .reverse()
      .map((message) => message.agent_metadata)
      .map((metadata) => (metadata?.ui_state as any)?.pending_permission)
      .find((permission) => permission?.part_id) || null;
  }, [messages]);

  const handleSubmitHitlDecisions = useCallback(async (permissionId: string, decisions: AgentHitlDecision[]) => {
    const response = await decideAgentPermission(permissionId, decisions);
    await upsertAgentSessionMessage(response.session);
    notify.success('HITL 决策已提交，Agent 正在继续执行');
  }, [upsertAgentSessionMessage]);

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
      ? '正在判断'
      : routingMode === 'chat'
        ? 'Chat'
        : '智能路由';
  const activeModelLabel = useCloudAI
    ? selectedCloudModel || '未选择模型'
    : settings.modelId || '未选择模型';
  const agentOptions = primaryAgents.map((agent) => ({ value: agent.id, label: agent.name }));
  const skillSourceOptions = agentSkillSources.map((source) => ({
    value: source.virtual_path,
    label: `${source.name}${source.skills.length ? ` (${source.skills.length})` : ''}`,
    disabled: !source.available,
  }));
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
  const workspaceAgentId = agentSessionOverview?.session?.agent_id || latestAgentMetadata?.active_agent_id || '';
  const workspaceAgentName = primaryAgents.find((agent) => agent.id === workspaceAgentId)?.name || workspaceAgentId || '';
  const agentWorkspace = useAgentWorkspace(latestAgentSessionId);
  const workspaceSelection = useAgentWorkspaceSelection(agentWorkspace.workspace);
  const asyncTasks = useAgentAsyncTasks(agentWorkspace);

  useEffect(() => {
    agentWorkspaceRefreshRef.current = agentWorkspace.refresh;
    return () => {
      if (agentWorkspaceRefreshRef.current === agentWorkspace.refresh) {
        agentWorkspaceRefreshRef.current = null;
      }
    };
  }, [agentWorkspace.refresh]);

  const openAgentInspector = useCallback(() => {
    setSidePanelOpen(true);
    setWorkbenchActiveTab('execution');
  }, []);

  const handleOpenAsyncTask = useCallback((taskId?: string, childSessionId?: string, options?: { expandDetail?: boolean }) => {
    if (taskId) {
      asyncTasks.focusTask(taskId);
      workspaceSelection.selectAsyncTask(taskId, childSessionId, options);
      if (options?.expandDetail) {
        asyncTasks.expandTask(taskId);
      }
    } else {
      workspaceSelection.selectRun();
    }
    setSidePanelOpen(true);
    setWorkbenchActiveTab('subagents');
  }, [asyncTasks, workspaceSelection]);

  const handleRunWorkspaceNextAction = useAgentWorkspaceNextActionRouter({
    agentWorkspace,
    workspaceSelection,
    openInspector: openAgentInspector,
    openWorkbenchTab: (tab) => {
      setSidePanelOpen(true);
      setWorkbenchActiveTab(tab);
    },
  });

  // Auto-detect running terminal from command parts and show dock
  useEffect(() => {
    for (let i = latestAgentParts.length - 1; i >= 0; i--) {
      const part = latestAgentParts[i];
      if (part?.type === 'command' && part.payload?.terminal_id) {
        const tid = String(part.payload.terminal_id);
        setActiveTerminalId(tid);
        if (part.status === 'running') setTerminalOpen(true);
        break;
      }
    }
  }, [latestAgentParts]);

  // 自动将最新待审批的或正在修改的变动文件在右侧编辑器中聚焦并打开（编辑器焦点跟随 + 实时流式 Diff）
  useEffect(() => {
    for (let i = latestAgentParts.length - 1; i >= 0; i--) {
      const part = latestAgentParts[i];
      if (part && part.type === 'diff') {
        const files = getChangedFilesFromPayload(part.payload);
        const firstFile = files[0];
        if (firstFile) {
          const name = firstFile.replace(/\\/g, '/').split('/').pop() || firstFile;
          const preview = part.content || '';
          const status = resolveArtifactStatus(part.status || 'modified');
          const hunks = preview ? parseDiffHunks(firstFile, preview) : undefined;

          const fileEntry: OpenedFile = {
            path: firstFile,
            name,
            content: preview,
            status,
            hunks,
            actionId: part.id || undefined,
          };

          setOpenedFiles((prev) => {
            const existingIdx = prev.findIndex((f) => f.path === firstFile);
            if (existingIdx >= 0) {
              const next = [...prev];
              const existing = next[existingIdx];
              if (existing) {
                // If it is the same file and has different preview content or status, update it!
                if (existing.content !== fileEntry.content || existing.status !== fileEntry.status) {
                  next[existingIdx] = {
                    ...existing,
                    content: fileEntry.content,
                    status: fileEntry.status,
                    hunks: fileEntry.hunks ?? existing.hunks,
                    actionId: fileEntry.actionId ?? existing.actionId,
                  };
                  return next;
                }
              }
              return prev; // No change, keep identity
            }
            return [...prev, fileEntry];
          });

          // 只有在 Part ID 发生改变时，才强制切换 Tab 聚焦，避免在同一个文件流式渲染期间强行覆盖用户的手动 Tab 切换
          if (lastAutoOpenedPartIdRef.current !== part.id) {
            lastAutoOpenedPartIdRef.current = part.id;
            setActiveFilePath(firstFile);
          }

          // 获取原始文件内容以用于 DiffEditor 比对
          if (status === 'modified' && latestAgentSessionId && part.id) {
            const matchedArtifact = agentSessionOverview?.artifacts?.find(
              (art) => art.source_part_id === part.id && art.path === firstFile
            );
            if (matchedArtifact) {
              void getArtifactOriginal(latestAgentSessionId, matchedArtifact.id).then((original: string | null) => {
                if (original === null) return;
                setOpenedFiles((prev) => prev.map((file) => (
                  file.path === firstFile ? { ...file, original } : file
                )));
              });
            }
          }
        }
        break;
      }
    }
  }, [latestAgentParts, latestAgentSessionId, agentSessionOverview?.artifacts]);


  const latestAgentPartsSignature = useMemo(() => {
    return latestAgentParts.map(p => `${p.id}:${p.status}:${p.updated_at || ''}`).join(',');
  }, [latestAgentParts]);

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
  }, [latestAgentSessionId, latestAgentPartsSignature, latestAgentStatus]);

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

  const handlePickFolder = useCallback(async () => {
    if (typeof window !== 'undefined' && (window as any).electronAPI?.selectFolder) {
      const folder: string | null = await (window as any).electronAPI.selectFolder(workspaceProjectPath || undefined);
      if (folder) { setWorkspaceProjectPath(folder); setShowPathEdit(false); }
      return;
    }

    try {
      const res = await browseFolderBackend(workspaceProjectPath || undefined);
      if (res.status === 'success' && res.path) {
        setWorkspaceProjectPath(res.path);
        setShowPathEdit(false);
        notify.success('选择路径成功');
      } else {
        setShowPathEdit((prev) => !prev);
        notify.info('本地选择器不可用，已开启手动输入');
      }
    } catch {
      setShowPathEdit((prev) => !prev);
      notify.info('本地选择器不可用，已开启手动输入');
    }
  }, [workspaceProjectPath]);

  const handlePathClick = useCallback(() => {
    if (!effectiveProjectPath) return;
    if (typeof window !== 'undefined' && (window as any).electronAPI?.openFolder) {
      void (window as any).electronAPI.openFolder(effectiveProjectPath);
      notify.success('正在打开本地文件夹...');
    } else {
      setShowPathEdit((prev) => !prev);
      notify.info('浏览器模式已激活路径输入，请手动打开/更改。');
    }
  }, [effectiveProjectPath]);

  const handleOpenFile = useCallback((artifact: (typeof agentFileSummaries)[number]) => {
    workspaceSelection.selectFile(artifact.path);
    const name = artifact.path.replace(/\\/g, '/').split('/').pop() || artifact.path;
    const status = resolveArtifactStatus(artifact.status);
    const hunks = status === 'modified' && artifact.preview
      ? parseDiffHunks(artifact.path, artifact.preview)
      : undefined;
    const fileEntry: OpenedFile = {
      path: artifact.path,
      name,
      content: artifact.preview || '',
      status,
      hunks,
      actionId: artifact.source_part_id || undefined,
    };
    setOpenedFiles((prev) => {
      const existingIdx = prev.findIndex((f) => f.path === artifact.path);
      if (existingIdx >= 0) {
        const next = [...prev];
        const existing = next[existingIdx];
        if (existing) {
          next[existingIdx] = { ...existing, content: fileEntry.content, status: fileEntry.status, hunks: fileEntry.hunks ?? existing.hunks, actionId: fileEntry.actionId ?? existing.actionId };
        }
        return next;
      }
      return [...prev, fileEntry];
    });
    setActiveFilePath(artifact.path);
    if (status === 'modified' && latestAgentSessionId) {
      void getArtifactOriginal(latestAgentSessionId, artifact.id).then((original: string | null) => {
        if (original === null) return;
        setOpenedFiles((prev) => prev.map((file) => (
          file.path === artifact.path ? { ...file, original } : file
        )));
      });
    }
  }, [latestAgentSessionId, workspaceSelection]);

  // ── Load workspace file tree when mode switches to 'workspace' ────────────────
  const loadWorkspaceTree = useCallback(async (projectPath: string) => {
    if (!projectPath) return;
    setWorkspaceTreeLoading(true);
    try {
      const result = await getWorkspaceTree({
        project_path: projectPath,
        max_depth: 4,
        limit: 400,
      });
      setWorkspaceTreeNodes(result.nodes);
      setWorkspaceTreeRoot(result.root);
      // Auto-expand top-level folders
      const topFolders = new Set<string>();
      for (const node of result.nodes) {
        if (node.kind === 'folder') topFolders.add(node.path);
      }
      setWsExpandedFolders(topFolders);
    } catch (err) {
      notify.error('加载工作区文件树失败');
    } finally {
      setWorkspaceTreeLoading(false);
    }
  }, []);

  useEffect(() => {
    if (fileTreeMode === 'workspace' && effectiveProjectPath) {
      void loadWorkspaceTree(effectiveProjectPath);
    }
  }, [fileTreeMode, effectiveProjectPath, loadWorkspaceTree]);

  // ── Open a file from the workspace disk tree ─────────────────────────────────
  const handleOpenWorkspaceFile = useCallback(async (node: WorkspaceTreeNode) => {
    if (node.kind !== 'file') return;
    const absPath = workspaceTreeRoot
      ? `${workspaceTreeRoot}/${node.path}`.replace(/\\/g, '/')
      : node.path;
    // Already open - just switch focus
    const existing = openedFiles.find((f) => f.path === absPath);
    if (existing) {
      setActiveFilePath(absPath);
      setRecentPaths((prev) => {
        const next = [absPath, ...prev.filter((p) => p !== absPath)];
        return next.slice(0, 10);
      });
      return;
    }

    try {
      const result = await readWorkspaceFile({
        file_path: absPath,
        project_path: effectiveProjectPath || undefined,
      });
      const fileName = node.name;
      const newFile: OpenedFile = {
        path: absPath,
        name: fileName,
        content: result.content,
        status: 'unknown',
        fromDisk: true,
      };
      setOpenedFiles((prev) => [...prev, newFile]);
      setActiveFilePath(absPath);
      setRecentPaths((prev) => {
        const next = [absPath, ...prev.filter((p) => p !== absPath)];
        return next.slice(0, 10);
      });
    } catch (err: any) {
      notify.error(`打开文件失败: ${extractApiErrorMessage(err, '未知错误')}`);
    }
  }, [openedFiles, workspaceTreeRoot, effectiveProjectPath]);

  const handleOpenWorkspacePath = useCallback(async (path: string) => {
    const normalized = path.replace(/\\/g, '/').replace(/^\/workspace\//, '');
    const node = workspaceFileNodes.find((item) => {
      if (item.kind !== 'file') return false;
      const itemPath = item.path.replace(/\\/g, '/');
      return itemPath === normalized || itemPath.endsWith(`/${normalized}`) || path.replace(/\\/g, '/') === itemPath;
    });
    if (!node) {
      notify.warning('当前文件树中未找到该文件，请先刷新工作区文件树。');
      setFileTreeMode('workspace');
      return;
    }
    await handleOpenWorkspaceFile(node);
  }, [handleOpenWorkspaceFile, workspaceFileNodes]);

  // ── Save file back to disk ────────────────────────────────────────────────────
  const handleSaveFile = useCallback(async (filePath: string, content: string) => {
    try {
      await writeWorkspaceFile({
        file_path: filePath,
        content,
        project_path: effectiveProjectPath || undefined,
      });
      notify.success(`已保存: ${filePath.split('/').pop() || filePath}`);
    } catch (err: any) {
      notify.error(`保存失败: ${extractApiErrorMessage(err, '未知错误')}`);
      throw err;
    }
  }, [effectiveProjectPath]);

  // ── Auto-detect terminal_id from latest agent parts ──────────────────────────
  // eslint-disable-next-line react-hooks/exhaustive-deps


  const handleAcceptHunk = useCallback((filePath: string, hunkId: string) => {
    setOpenedFiles((prev) => {
      const file = prev.find((f) => f.path === filePath);
      if (!file) return prev;
      return prev.map((f) => {
        if (f.path !== filePath) return f;
        return { ...f, hunks: (f.hunks ?? []).map((h) => h.id === hunkId ? { ...h, status: 'accepted' as const } : h) };
      });
    });
  }, []);

  const handleRejectHunk = useCallback((filePath: string, hunkId: string) => {
    setOpenedFiles((prev) => {
      const file = prev.find((f) => f.path === filePath);
      if (!file) return prev;
      return prev.map((f) => {
        if (f.path !== filePath) return f;
        return { ...f, hunks: (f.hunks ?? []).map((h) => h.id === hunkId ? { ...h, status: 'rejected' as const } : h) };
      });
    });
  }, []);

  const handleAcceptAll = useCallback((filePath: string) => {
    setOpenedFiles((prev) => prev.map((f) => {
      if (f.path !== filePath) return f;
      return { ...f, hunks: (f.hunks ?? []).map((h) => h.status === 'pending' ? { ...h, status: 'accepted' as const } : h) };
    }));
  }, []);

  const handleRejectAll = useCallback((filePath: string) => {
    setOpenedFiles((prev) => prev.map((f) => {
      if (f.path !== filePath) return f;
      return { ...f, hunks: (f.hunks ?? []).map((h) => h.status === 'pending' ? { ...h, status: 'rejected' as const } : h) };
    }));
  }, []);

  const handleCloseEditorTab = useCallback((closedPath: string) => {
    setOpenedFiles((prev) => prev.filter((f) => f.path !== closedPath));
    setActiveFilePath((current) => {
      if (current !== closedPath) return current;
      const remaining = openedFiles.filter((f) => f.path !== closedPath);
      if (remaining.length === 0) return null;
      const idx = openedFiles.findIndex((f) => f.path === closedPath);
      return remaining[Math.min(idx, remaining.length - 1)]?.path ?? null;
    });
  }, [openedFiles]);

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
      const icon = getFileIcon(node.name);
      const isText = isTextIcon(icon.icon);
      return (
        <div
          key={node.path}
          className={`${styles.agentFileCard} ${styles.agentFileCardClickable}`}
          style={{ ['--file-depth' as any]: String(depth) }}
          onClick={() => handleOpenFile(file)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && handleOpenFile(file)}
        >
          <div className={styles.agentFileTreeRow}>
            <div className={styles.agentFileTreeLine} aria-hidden="true">
              <span className={styles.agentFileTreeBranch} />
              <span className={styles.agentFileTreeDot} data-tone={statusTone} />
            </div>
            <div className={styles.agentFileCardBody}>
              <div className={styles.agentFileCardTop}>
                <div className={styles.agentFilePath} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span
                    className={isText ? styles.iconBadge : styles.iconEmoji}
                    style={{ ['--icon-color' as any]: icon.color }}
                  >
                    {icon.icon}
                  </span>
                  <span>{node.name}</span>
                </div>
                <Tag className={styles.agentFileStatus} color={statusTone}>{file.status || 'modified'}</Tag>
              </div>
              <div className={styles.agentFileSummary}>{file.summary}</div>
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
              <span className={styles.agentFolderEmoji} style={{ marginRight: '4px', fontSize: '14px' }}>
                {isExpanded ? '📂' : '📁'}
              </span>
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
  }, [expandedFolders, handleOpenFile, toggleFolder]);

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
      skillSourceOptions={skillSourceOptions}
      selectedSkillSources={selectedSkillSources}
      onSkillSourcesChange={(sources) => {
        setSkillsInitialized(true);
        setSelectedSkillSources(sources);
      }}
      skillsLoading={skillsLoading}
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
      enableTypewriter={false}
      onRetry={handleRetry}
      onEdit={handleEditMessage}
      onDelete={deleteMessage}
      knowledge_sources={msg.knowledge_sources}
      retrieval_info={msg.retrieval_info}
      agent_metadata={msg.agent_metadata}
      agentFlowPosition={agentFlowPosition}
      onRefreshAgentRun={handleRefreshAgentRun}
      onOpenAsyncTask={handleOpenAsyncTask}
    />
    );
  }, [
    isActivelyStreaming,
    messages.length,
    handleRetry,
    handleEditMessage,
    deleteMessage,
    handleRefreshAgentRun,
    handleOpenAsyncTask,
  ]);

  const slimFilePanel = useMemo(() => {
    const renderWsNode = (node: WorkspaceTreeNode, depth = 0): React.ReactNode => {
      if (node.kind === 'file') {
        const icon = getFileIcon(node.name);
        const isText = isTextIcon(icon.icon);
        return (
          <div
            key={node.path}
            className={`${styles.agentFileCard} ${styles.agentFileCardClickable}`}
            style={{ ['--file-depth' as any]: String(depth), margin: '0 4px 3px' }}
            onClick={() => {
              workspaceSelection.selectFile(node.path);
              void handleOpenWorkspaceFile(node);
            }}
            onFocus={() => workspaceSelection.selectFile(node.path)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                workspaceSelection.selectFile(node.path);
                void handleOpenWorkspaceFile(node);
              }
            }}
          >
            <div className={styles.agentFileCardBody} style={{ padding: '8px 8px 8px 0' }}>
              <div className={styles.agentFileCardTop}>
                <div className={styles.agentFilePath} style={{ paddingLeft: `${depth * 10}px`, display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span
                    className={isText ? styles.iconBadge : styles.iconEmoji}
                    style={{ ['--icon-color' as any]: icon.color }}
                  >
                    {icon.icon}
                  </span>
                  <span>{node.name}</span>
                </div>
              </div>
            </div>
          </div>
        );
      }
      if (node.kind === 'folder') {
        const isExpanded = wsExpandedFolders.has(node.path);
        return (
          <div key={node.path} className={styles.agentFolderGroup} style={{ ['--folder-depth' as any]: String(depth) }}>
            <button
              type="button"
              className={styles.agentFolderRow}
              onClick={() => setWsExpandedFolders((prev) => { const next = new Set(prev); if (next.has(node.path)) next.delete(node.path); else next.add(node.path); return next; })}
            >
              <span className={`${styles.agentFolderChevron} ${isExpanded ? styles.agentFolderChevronOpen : ''}`}>▸</span>
              <span className={styles.agentFolderEmoji} style={{ marginRight: '4px', fontSize: '14px' }}>
                {isExpanded ? '📂' : '📁'}
              </span>
              <span className={styles.agentFolderName}>{node.name}</span>
            </button>
            {isExpanded && node.children && (
              <div className={styles.agentFolderChildren}>
                {node.children.map((child) => renderWsNode(child, depth + 1))}
              </div>
            )}
          </div>
        );
      }
      return null;
    };

    return (
      <div className={styles.slimFilePanel}>
        <div className={styles.slimFilePanelHeader}>
          <div className={styles.fileTreeToggle}>
            <button
              type="button"
              className={`${styles.fileTreeToggleBtn} ${fileTreeMode === 'agent' ? styles.fileTreeToggleBtnActive : ''}`}
              onClick={() => setFileTreeMode('agent')}
            >变更</button>
            <button
              type="button"
              className={`${styles.fileTreeToggleBtn} ${fileTreeMode === 'workspace' ? styles.fileTreeToggleBtnActive : ''}`}
              onClick={() => { setFileTreeMode('workspace'); }}
            >工作区</button>
          </div>
          {fileTreeMode === 'agent' && agentFileSummaries.length > 0 && (
            <span className={styles.slimFileCount}>{agentFileSummaries.length}</span>
          )}
          {fileTreeMode === 'workspace' && (
            <button
              type="button"
              className={styles.fileTreeRefreshBtn}
              onClick={() => void loadWorkspaceTree(effectiveProjectPath)}
              disabled={workspaceTreeLoading}
              title="刷新文件树"
            >↺</button>
          )}
        </div>
        {fileTreeMode === 'agent' ? (
          agentFileSummaries.length > 0 ? (
            <div className={styles.slimFileList}>
              {renderTreeNode(agentFileTree)}
            </div>
          ) : (
            <div className={styles.agentFileEmpty}>暂无变更文件</div>
          )
        ) : (
          workspaceTreeLoading ? (
            <div className={styles.agentFileEmpty}>正在加载文件树…</div>
          ) : workspaceTreeNodes.length > 0 ? (
            <div className={styles.slimFileList}>
              {workspaceTreeNodes.map((node) => renderWsNode(node))}
            </div>
          ) : (
            <div className={styles.agentFileEmpty}>
              {effectiveProjectPath ? '文件树为空或无法访问' : '请先选择工作区目录'}
            </div>
          )
        )}
      </div>
    );
  }, [
    agentFileSummaries, agentFileTree, renderTreeNode,
    fileTreeMode, workspaceTreeNodes, workspaceTreeLoading, wsExpandedFolders,
    effectiveProjectPath, handleOpenWorkspaceFile, loadWorkspaceTree, workspaceSelection,
  ]);

  const editorContent = useMemo(() => (
    <div className={styles.editorWithTerminal}>
      <div className={styles.editorPaneMain}>
        <AgentWorkspaceEditor
          openedFiles={openedFiles}
          activeFilePath={activeFilePath}
          onTabChange={setActiveFilePath}
          onTabClose={handleCloseEditorTab}
          onActiveContextChange={handleActiveEditorContextChange}
          onAcceptHunk={handleAcceptHunk}
          onRejectHunk={handleRejectHunk}
          onAcceptAll={handleAcceptAll}
          onRejectAll={handleRejectAll}
          onSave={handleSaveFile}
          activeTerminalId={activeTerminalId}
          onToggleTerminal={() => setTerminalOpen((o) => !o)}
          terminalOpen={terminalOpen}
          workspaceRoot={workspaceTreeRoot}
          onBreadcrumbClick={handleBreadcrumbClick}
        />
      </div>
      {terminalOpen && activeTerminalId && (
        <div
          className={styles.terminalDock}
          style={{ height: terminalHeight, minHeight: 120, maxHeight: '60%' }}
        >
          <div
            className={`${styles.terminalDockResizer} ${resizingTerminal ? styles.terminalDockResizerActive : ''}`}
            onPointerDown={handleTerminalSplitterPointerDown}
          />
          <div className={styles.terminalDockBar}>
            <span className={styles.terminalDockTitle}>▷ Terminal</span>
            <button
              type="button"
              className={styles.terminalDockClose}
              onClick={() => setTerminalOpen(false)}
              aria-label="关闭终端"
            >×</button>
          </div>
          <AgentTerminal
            terminalId={activeTerminalId}
            running={latestAgentStatus === 'running'}
          />
        </div>
      )}
    </div>
  ), [
    openedFiles, activeFilePath, handleCloseEditorTab,
    handleAcceptHunk, handleRejectHunk, handleAcceptAll, handleRejectAll,
    handleSaveFile, handleActiveEditorContextChange, activeTerminalId, terminalOpen, latestAgentStatus,
    workspaceTreeRoot, handleBreadcrumbClick, terminalHeight, resizingTerminal,
    handleTerminalSplitterPointerDown,
  ]);

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

  const agentIdeWorkspace = (
    <section className={styles.agentIdeWorkspace} style={{ flex: '1 1 0', minWidth: 0 }} aria-label="AI 编程工作区">
      <div className={styles.agentIdeHeader}>
        <div style={{ minWidth: 0 }}>
          <div className={styles.agentIdeKicker}>Agent IDE</div>
          <div className={styles.agentIdeTitle}>代码审阅与补丁确认</div>
          {effectiveProjectPath ? (
            <div
              className={styles.agentIdePath}
              title={typeof window !== 'undefined' && (window as any).electronAPI ? '点击打开本地文件夹' : '点击编辑项目路径'}
              onClick={handlePathClick}
            >
              <FolderOpenOutlined style={{ fontSize: 10, opacity: 0.7 }} />
              <span className={styles.agentIdePathText}>{effectiveProjectPath}</span>
            </div>
          ) : (
            <div className={styles.agentIdePathEmpty}>未绑定工作区目录</div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flex: '0 0 auto' }}>
          <Tooltip title={typeof window !== 'undefined' && (window as any).electronAPI ? '选择本地项目文件夹' : '手动输入项目路径'}>
            <Button size="small" icon={<FolderOpenOutlined />} onClick={() => void handlePickFolder()}>
              {effectiveProjectPath ? '更换' : '选择文件夹'}
            </Button>
          </Tooltip>
          <Tag color={openedFiles.length ? 'processing' : 'default'} className={styles.agentIdeTag}>
            {openedFiles.length ? `${openedFiles.length} opened` : 'No file opened'}
          </Tag>
        </div>
      </div>
      {showPathEdit && (
        <div className={styles.agentIdePathEdit}>
          <Input
            size="small"
            prefix={<FolderOpenOutlined style={{ opacity: 0.5 }} />}
            placeholder="例如：C:\\Projects\\my-app"
            value={workspaceProjectPath}
            onChange={(e) => setWorkspaceProjectPath(e.target.value)}
            onPressEnter={() => setShowPathEdit(false)}
            autoFocus
            suffix={
              <Button type="link" size="small" style={{ height: 20, padding: 0 }} onClick={() => setShowPathEdit(false)}>确认</Button>
            }
          />
        </div>
      )}
      <div className={styles.agentIdeBody}>
        <aside className={styles.agentIdeTreePane}>{slimFilePanel}</aside>
        <main className={styles.agentIdeEditorPane}>{editorContent}</main>
      </div>
    </section>
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


  return (
    <div
      className={styles.chatContainer}
      style={isMobile ? { height: 'calc(100vh - 64px)' } : undefined}
    >
      <div style={{ display: 'none' }}>
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
      </div>
      {isDesktop && latestAgentSessionId && (
        <AgentWorkspaceStatusBar
          agentName={workspaceAgentName}
          sessionStatus={latestAgentStatus}
          asyncMetrics={agentWorkspace.workspace?.async_tasks.metrics ?? null}
          onOpenAsyncTasks={() => handleOpenAsyncTask()}
        />
      )}
      <div className={styles.chatWorkspace}>
        <main className={styles.mainChatPane} style={{ flex: `0 0 ${chatPaneWidth}px`, minWidth: 0, ...(isDesktop && !chatPanelOpen ? { flexBasis: 0, overflow: 'hidden', opacity: 0, pointerEvents: 'none' } : {}) }}>
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

          <div className={styles.composerAnchor}>
            <HitlApprovalPanel
              pendingPermission={pendingApproval}
              prefersReducedMotion={Boolean(prefersReducedMotion)}
              onSubmit={handleSubmitHitlDecisions}
            />

            <ChatInput
              onSend={handleSend}
              onStop={handleStopCurrentRun}
              onClear={handleClearChat}
              onNewChat={() => createSession()}
              disabled={!settings.modelId && !useCloudAI}
              loading={isLoading}
              isStreaming={isActivelyStreaming || isAgentSessionRunning}
              modelId={useCloudAI ? selectedCloudModel : settings.modelId}
              agentModeAvailable={primaryAgents.length > 0}
              routingMode={routingMode}
              routing={routingIntent}
              autonomyMode={autonomyMode}
              workspaceFiles={workspaceFileNodes}
              projectPath={effectiveProjectPath || undefined}
              selectedMentions={explicitContextMentions}
              onMentionsChange={setExplicitContextMentions}
              activeFileContext={activeFileContext}
            />
          </div>
        </main>

        {isDesktop && (
          <div
            className={`${styles.splitter} ${resizingChatPane && chatPanelOpen ? styles.splitterDragging : ''} ${!chatPanelOpen ? styles.splitterCollapsed : ''}`}
            role="separator"
            aria-orientation="vertical"
            aria-label="调整聊天区和 IDE 工作区宽度"
            onPointerDown={chatPanelOpen ? handleChatSplitterPointerDown : undefined}
          >
            <button
              type="button"
              className={styles.splitterToggleBtn}
              onClick={() => setChatPanelOpen((o) => !o)}
              aria-label={chatPanelOpen ? '收起左侧对话栏' : '展开左侧对话栏'}
              title={chatPanelOpen ? '收起左侧对话栏' : '展开左侧对话栏'}
            >
              {chatPanelOpen ? '‹' : '›'}
            </button>
          </div>
        )}
        {isDesktop && agentIdeWorkspace}

        {isDesktop && (
          <>
            <div
              className={`${styles.splitter} ${resizingSidePanel && sidePanelOpen ? styles.splitterDragging : ''} ${!sidePanelOpen ? styles.splitterCollapsed : ''}`}
              role="separator"
              aria-orientation="vertical"
              aria-label="调整聊天区和工具区宽度"
              onPointerDown={sidePanelOpen ? handleSplitterPointerDown : undefined}
            >
              <button
                type="button"
                className={styles.splitterToggleBtn}
                onClick={() => setSidePanelOpen((o) => !o)}
                aria-label={sidePanelOpen ? '收起右侧面板' : '展开右侧面板'}
                title={sidePanelOpen ? '收起右侧面板' : '展开右侧面板'}
              >
                {sidePanelOpen ? '›' : '‹'}
              </button>
            </div>
            {sidePanelOpen && (
              <div className={styles.sidePanels} style={{ flex: `0 0 ${sidePanelWidth}px` }}>
                <AgentWorkspaceContainer
                  activeKey={workbenchActiveTab}
                  onActiveKeyChange={setWorkbenchActiveTab}
                  changedFiles={agentFileSummaries.length}
                  runContent={workbenchRunPanel}
                  configContent={React.cloneElement(contextPanel, { embedded: true })}
                  progressContent={workbenchProgressPanel}
                  fileTreeContent={slimFilePanel}
                  agentWorkspace={agentWorkspace}
                  asyncTasks={asyncTasks}
                  workspaceSelection={workspaceSelection}
                  sessionId={latestAgentSessionId}
                  onSubmitPermission={handleSubmitHitlDecisions}
                  onOpenFile={handleOpenWorkspacePath}
                  onRunNextAction={handleRunWorkspaceNextAction}
                />
              </div>
            )}
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
          skillSourceOptions={skillSourceOptions}
          selectedSkillSources={selectedSkillSources}
          onSkillSourcesChange={(sources) => {
            setSkillsInitialized(true);
            setSelectedSkillSources(sources);
          }}
          skillsLoading={skillsLoading}
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
          return deleteSession(id);
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

      <QuickFileOpener
        open={quickOpenVisible}
        onClose={() => setQuickOpenVisible(false)}
        nodes={workspaceTreeNodes}
        rootPath={workspaceTreeRoot}
        onSelectFile={handleOpenWorkspaceFile}
        recentPaths={recentPaths}
      />

    </div>
  );
};

export default ChatPage;
