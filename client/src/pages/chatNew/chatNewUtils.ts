import type { OpenedFile } from '../../components/chat/AgentWorkspaceEditor';

export interface APIKeyConfig {
  provider: string;
  api_key?: string;
  key_id?: string;
  model?: string;
  group_id?: string;
  base_url?: string;
}

export const AGENT_MODEL_PROVIDER_ALIASES: Record<string, string> = {
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

export function resolveAgentModelConfig(params: {
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

export const STARTER_IDEAS = [
  { title: '学习与规划', desc: '帮我制定一个深度学习入门计划', icon: '📚' },
  { title: '模型微调', desc: '如何进行大模型 QLoRA 微调？', icon: '⚡' },
  { title: '代码助理', desc: '用 Python 写一个分布式爬虫示例', icon: '💻' },
  { title: '数据分析', desc: '分析当前大语言模型的技术趋势', icon: '📊' },
];

export const sectionMotion = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.26, ease: [0.23, 1, 0.32, 1] as const },
};

export interface StoredChatScrollState {
  topIndex: number;
  atBottom: boolean;
  updatedAt: string;
}

export const CHAT_SCROLL_STORAGE_KEY = 'chat_scroll_positions_v1';
export const INTENT_ROUTING_TIMEOUT_MS = 8000;
export const CHAT_WORKSPACE_ID_STORAGE_KEY = 'chat_workspace_id_v1';
export const CHAT_PROJECT_PATH_STORAGE_KEY = 'chat_project_path_v1';
export const CHAT_WORKSPACE_EVENT = 'chat-workspace-change';
export const CHAT_SIDE_PANEL_WIDTH_STORAGE_KEY = 'chat_side_panel_width_v1';
export const CHAT_PANE_WIDTH_STORAGE_KEY = 'chat_chat_pane_width_v1';
export const CHAT_SIDE_PANEL_OPEN_STORAGE_KEY = 'chat_side_panel_open_v1';
export const CHAT_PANEL_OPEN_STORAGE_KEY = 'chat_chat_panel_open_v1';
export const CHAT_AGENT_SKILL_SOURCES_STORAGE_KEY = 'chat_agent_skill_sources_v1';

export const resolveArtifactStatus = (statusRaw: string): OpenedFile['status'] => {
  const s = statusRaw.toLowerCase();
  if (/add|new|create|新增/.test(s)) return 'added';
  if (/delete|remove|removed|删除/.test(s)) return 'deleted';
  if (/modify|update|change|edit|fix|modified|修改/.test(s)) return 'modified';
  return 'unknown';
};

export const getChangedFilesFromPayload = (payload?: Record<string, any>) => {
  const files = payload?.changed_files || payload?.payload?.changed_files || payload?.files || payload?.payload?.files || [];
  if (!Array.isArray(files)) return [];
  return files.map((item: any) => (typeof item === 'string' ? item : item?.path || item?.file_path)).filter(Boolean) as string[];
};

export const withTimeout = async <T,>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> => {
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

export const clampMessageIndex = (index: number, messageCount: number) => {
  if (messageCount <= 0) return 0;
  return Math.min(Math.max(index, 0), messageCount - 1);
};

export const readStoredScrollMap = (): Record<string, StoredChatScrollState> => {
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

export const getStoredScrollState = (sessionId: string | null): StoredChatScrollState | null => {
  if (!sessionId) return null;
  return readStoredScrollMap()[sessionId] || null;
};

export const persistScrollState = (
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
