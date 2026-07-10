/**
 * API service layer.
 * Handles connection reuse, request cancellation, and automatic retry logic.
 */
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';

// Resolve backend API base URL.
const getApiBaseUrl = () => {
  if (typeof window !== 'undefined' && (window as any).electronAPI) {
    return (window as any).electronAPI.getBackendUrlSync?.() || `http://${window.location.hostname}:8010`;
  }
  const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
  return ((import.meta as any).env?.VITE_API_URL || `http://${host}:8010`) as string;
};

// Export base URL for other modules.
export const API_BASE_URL = getApiBaseUrl();

export const getAgentTerminalWebSocketUrl = (terminalId: string): string => {
  const base = API_BASE_URL.replace(/^http/i, 'ws').replace(/\/$/, '');
  return `${base}/agent-terminals/${encodeURIComponent(terminalId)}/ws`;
};

// ==================== Connection Pool ====================

interface ConnectionPoolEntry {
  controller: AbortController;
  timestamp: number;
  requestType: string;
}

class ConnectionPool {
  private pool: Map<string, ConnectionPoolEntry> = new Map();
  private maxConnections: number = 50;
  private cleanupInterval: number = 60000;
  private cleanupTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.startCleanup();
  }

  generateKey(url: string, method: string): string {
    return `${method}:${url}`;
  }

  acquire(key: string, requestType: string = 'default'): AbortController {
    if (this.pool.size >= this.maxConnections) {
      this.cleanup();
    }

    const controller = new AbortController();
    this.pool.set(key, {
      controller,
      timestamp: Date.now(),
      requestType,
    });

    return controller;
  }

  release(key: string): void {
    // Remove from pool only; completed requests should not be aborted here.
    this.pool.delete(key);
  }

  abortByKey(key: string): void {
    const entry = this.pool.get(key);
    if (entry) {
      entry.controller.abort();
      this.pool.delete(key);
    }
  }

  hasKey(key: string): boolean {
    return this.pool.has(key);
  }

  abortByType(requestType: string): void {
    const keysToRemove: string[] = [];
    this.pool.forEach((entry, key) => {
      if (entry.requestType === requestType) {
        entry.controller.abort();
        keysToRemove.push(key);
      }
    });
    keysToRemove.forEach((key) => this.pool.delete(key));
  }

  abortAll(): void {
    this.pool.forEach((entry) => {
      if (!entry.controller.signal.aborted) {
        entry.controller.abort();
      }
    });
    this.pool.clear();
  }

  getActiveCount(): number {
    return this.pool.size;
  }

  private cleanup(): void {
    const now = Date.now();
    const staleThreshold = 300000;
    const keysToRemove: string[] = [];

    this.pool.forEach((entry, key) => {
      if (now - entry.timestamp > staleThreshold || entry.controller.signal.aborted) {
        keysToRemove.push(key);
      }
    });

    keysToRemove.forEach((key) => this.pool.delete(key));
  }

  // ==================== Retry Logic ====================

  private startCleanup(): void {
    this.cleanupTimer = setInterval(() => this.cleanup(), this.cleanupInterval);
  }

  destroy(): void {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer);
    }
    this.abortAll();
  }
}

const connectionPool = new ConnectionPool();

// ==================== Retry Logic ====================

interface RetryConfig {
  maxRetries: number;
  baseDelay: number;
  maxDelay: number;
  retryableErrors: string[];
}

const defaultRetryConfig: RetryConfig = {
  maxRetries: 3,
  baseDelay: 1000,
  maxDelay: 10000,
  retryableErrors: [
    'ECONNRESET',
    'ENOTFOUND',
    'ETIMEDOUT',
    'ECONNABORTED',
    'network error',
    'fetch failed',
    'aborted',
  ],
};

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function calculateBackoff(attempt: number, baseDelay: number, maxDelay: number): number {
  const exponentialDelay = baseDelay * Math.pow(2, attempt);
  const jitter = Math.random() * 100;
  return Math.min(exponentialDelay + jitter, maxDelay);
}

function isRetryableError(error: any): boolean {
  const errorMessage = error?.message?.toLowerCase() || '';
  const errorCode = error?.code?.toLowerCase() || '';

  return defaultRetryConfig.retryableErrors.some(
    (retryableError) =>
      errorMessage.includes(retryableError.toLowerCase()) ||
      errorCode.includes(retryableError.toLowerCase()),
  );
}

export async function fetchWithRetry<T>(
  fetchFn: () => Promise<T>,
  config: Partial<RetryConfig> = {},
): Promise<T> {
  const retryConfig = { ...defaultRetryConfig, ...config };
  let lastError: Error | null = null;

  for (let attempt = 0; attempt < retryConfig.maxRetries; attempt++) {
    try {
      return await fetchFn();
    } catch (error: any) {
      lastError = error;

      if (error.name === 'AbortError') {
        throw error;
      }

      if (!isRetryableError(error)) {
        throw error;
      }

      if (attempt < retryConfig.maxRetries - 1) {
        const backoffDelay = calculateBackoff(attempt, retryConfig.baseDelay, retryConfig.maxDelay);
        console.warn(
          `Request failed, retrying in ${Math.round(backoffDelay)}ms (${attempt + 1}/${retryConfig.maxRetries})`,
          error.message,
        );
        await delay(backoffDelay);
      }
    }
  }

  throw lastError;
}

// ==================== Request Cache & Offline Queue ====================

const GET_CACHE_TTL = 10000; // 10秒
const getCacheMap = new Map<string, { timestamp: number; data: any; promise?: Promise<any> }>();

interface OfflineRequest {
  config: any;
  resolve: (value: any) => void;
  reject: (reason?: any) => void;
}
let offlineQueue: OfflineRequest[] = [];
// isOnline 可以在后续与后端健康状态同步，或者作为导出变量

export const processOfflineQueue = () => {
  if (offlineQueue.length > 0) {
    const queue = [...offlineQueue];
    offlineQueue = [];
    queue.forEach(({ config, resolve, reject }) => {
      apiClient(config).then(resolve).catch(reject);
    });
  }
};

// ==================== Axios Instance Creation ====================

const createAxiosInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: API_BASE_URL,
    timeout: 300000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // GET 请求白名单（缓存和防并发）
  const CACHEABLE_GET_URLS = [
    '/model-center/suggestions',
    '/model-center/source',
  ];

  instance.interceptors.request.use(
    (config) => {
      const url = config.url || '';
      const method = (config.method || 'get').toLowerCase();
      
      // GET 请求缓存处理
      if (method === 'get' && CACHEABLE_GET_URLS.some(u => url.includes(u))) {
        const cacheKey = url;
        const cached = getCacheMap.get(cacheKey);
        
        if (cached && Date.now() - cached.timestamp < GET_CACHE_TTL) {
          // 如果有正在进行的相同请求，或者已有有效数据
          if (cached.promise || cached.data) {
             const controller = new AbortController();
             config.signal = controller.signal;
             controller.abort('CACHED'); // 提前中断，在 response error 中处理
             (config as any)._cacheKey = cacheKey;
             return config;
          }
        }
      }

      // POST 防抖 (连击防护)
      // 生成包含 body 的 hash key
      let bodyStr = '';
      if (config.data) {
        if (config.data instanceof FormData) {
          // 不对 FormData 进行完整内容防抖，或者使用随机数避免误杀
          bodyStr = `FormData_${Date.now()}_${Math.random()}`;
        } else {
          try {
            bodyStr = JSON.stringify(config.data);
          } catch {
            bodyStr = 'Unstringifiable';
          }
        }
      }
      const debounceKey = `${method}:${url}:${bodyStr}`;
      
      if (method === 'post' || method === 'put') {
         if (connectionPool.hasKey(debounceKey)) {
             const controller = new AbortController();
             config.signal = controller.signal;
             controller.abort('DEBOUNCED');
             return config;
         }
         const controller = connectionPool.acquire(debounceKey, 'axios');
         config.signal = controller.signal;
         (config as any)._debounceKey = debounceKey;
      } else {
        // 普通请求
        const key = connectionPool.generateKey(url, method);
        const controller = connectionPool.acquire(key, 'axios');
        config.signal = controller.signal;
        (config as any)._connectionKey = key;
      }
      
      return config;
    },
    (error) => {
      return Promise.reject(error);
    },
  );

  instance.interceptors.response.use(
    (response) => {
      const key = (response.config as any)?._connectionKey;
      if (key) {
        connectionPool.release(key);
      }
      const debounceKey = (response.config as any)?._debounceKey;
      if (debounceKey) {
        connectionPool.release(debounceKey);
      }

      // GET 缓存记录
      const method = (response.config.method || 'get').toLowerCase();
      const url = response.config.url || '';
      if (method === 'get' && CACHEABLE_GET_URLS.some(u => url.includes(u))) {
        const cacheKey = url;
        getCacheMap.set(cacheKey, { timestamp: Date.now(), data: response.data });
      }

      return response;
    },
    (error) => {
      const config = error.config as any;
      
      // 处理拦截的请求
      if (axios.isCancel(error)) {
         if (error.message === 'CACHED' && config._cacheKey) {
            const cached = getCacheMap.get(config._cacheKey);
            if (cached?.data) {
                // 伪造成功 response
                return Promise.resolve({
                   data: cached.data,
                   status: 200,
                   statusText: 'OK',
                   headers: {},
                   config: config,
                   request: {}
                });
            } else if (cached?.promise) {
               return cached.promise.then(data => ({
                   data,
                   status: 200,
                   statusText: 'OK',
                   headers: {},
                   config: config,
                   request: {}
               }));
            }
         }
         if (error.message === 'DEBOUNCED') {
             return Promise.reject(new Error('请求防抖，请勿重复点击'));
         }
      }

      const key = config?._connectionKey;
      if (key) {
        connectionPool.release(key);
      }
      const debounceKey = config?._debounceKey;
      if (debounceKey) {
        connectionPool.release(debounceKey);
      }

      // 处理离线缓冲（仅网络断开或超时，不含 500 服务端错误；跳过 FormData 因为不可重放）
      if (error.message === 'Network Error' || error.code === 'ECONNABORTED') {
         const url = String(config?.url || '');
         const isFormData = config?.data instanceof FormData;
         const shouldQueue = config && !isFormData && ['post', 'put', 'patch', 'delete'].includes((config.method || '').toLowerCase())
           && !url.includes('/agent-sessions/');
         if (shouldQueue) {
            return new Promise((resolve, reject) => {
               offlineQueue.push({ config, resolve, reject });
            });
         }
      }

      const suppressErrorLogging = Boolean(config?.suppressErrorLogging);

      if (!suppressErrorLogging && !axios.isCancel(error)) {
        if (error.response) {
          const responseData = error.response.data;
          const detail =
            typeof responseData === 'string'
              ? responseData
              : responseData?.detail || responseData?.message || JSON.stringify(responseData);
          console.error('[API] Error', {
            status: error.response.status,
            method: String(config?.method || '').toUpperCase(),
            url: config?.url,
            detail,
            data: responseData,
          });
        } else if (error.request) {
          console.error('[API] Network Error', {
            method: String(config?.method || '').toUpperCase(),
            url: config?.url,
            message: error.message,
          });
        } else {
          console.error('[API] Error', {
            method: String(config?.method || '').toUpperCase(),
            url: config?.url,
            message: error.message,
          });
        }
      }
      return Promise.reject(error);
    },
  );

  return instance;
};

export const apiClient = createAxiosInstance();

// ==================== Request Manager ====================

export const requestManager = {
  cancelRequest(key: string): void {
    connectionPool.abortByKey(key);
  },

  cancelByType(requestType: string): void {
    connectionPool.abortByType(requestType);
  },

  cancelAll(): void {
    connectionPool.abortAll();
  },

  getActiveRequestCount(): number {
    return connectionPool.getActiveCount();
  },
};

export interface ChatAgentIntentRequest {
  content: string;
  provider?: string;
  model?: string;
  agent_id?: string;
  chat_session_id?: string;
  routing_mode?: 'auto' | 'chat' | 'agent';
  active_context?: ActiveFileContext | null;
  explicit_context?: ExplicitContextMention[];
}

export interface ChatAgentIntentResponse {
  mode: 'chat' | 'agent';
  confidence: number;
  reason: string;
  source: 'local_rule' | 'cloud' | 'fallback' | 'manual';
  suggested_agent_id?: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  description?: string;
  mode: 'primary' | 'subagent' | 'all' | string;
  system_prompt?: string;
  output_requirements?: string;
  default_provider?: string;
  default_model?: string;
  max_iterations?: number;
  tools?: string[];
  handoff_targets?: string[];
  async_subagent_targets?: string[];
  hidden?: boolean;
  schema_version?: number | string;
  definition_format?: 'agent_manifest_v2' | 'runtime' | string;
  system_prompt_definition?: {
    identity?: string;
    role?: string;
    tone?: string;
    responsibilities?: string[];
    constraints?: string[];
    workflow?: unknown[];
    sections?: Record<string, unknown>;
  };
  output_schema?: {
    format?: string;
    instructions?: string;
    required_sections?: string[];
    required_fields?: string[];
    schema?: Record<string, unknown>;
  };
  few_shot_examples?: Array<{
    name?: string;
    user?: string;
    assistant?: string;
    context?: string;
  }>;
  reflection_rules?: {
    before_tool_use?: string[];
    before_edit?: string[];
    before_final?: string[];
    on_error?: string[];
    rules?: string[];
    sections?: Record<string, unknown>;
  };
  tool_policy?: {
    allowed?: string[];
    denied?: string[];
    notes?: string;
  };
  handoff_policy?: {
    targets?: string[];
    async_targets?: string[];
    notes?: string;
  };
  metadata?: Record<string, unknown>;
  runtime_policy?: AgentRuntimePolicy;
  execution_plan?: AgentExecutionPlan;
}

export interface AgentSessionCreate {
  chat_session_id?: string;
  agent_id?: string;
  title?: string;
  project_path?: string;
  workspace_id?: string;
  task_mode?: 'build' | 'train' | 'hybrid';
  provider?: string;
  model?: string;
  autonomy_mode?: 'safe_auto' | 'confirm_all' | 'read_only';
  enabled_skill_sources?: string[] | null;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  description?: string;
  local_path?: string | null;
  created_at: string;
  updated_at: string;
  document_count: number;
  vector_count: number;
  vector_collection_name?: string;
  status?: string;
}

export interface WorkspaceTreeNode {
  name: string;
  path: string;
  kind: 'folder' | 'file';
  children?: WorkspaceTreeNode[];
}

export interface WorkspaceTreeResponse {
  root: string;
  nodes: WorkspaceTreeNode[];
  truncated: boolean;
}

export interface WorkspaceCreateRequest {
  name: string;
  description?: string;
  local_path?: string;
}

export interface WorkspaceUpdateRequest {
  name?: string;
  description?: string;
  local_path?: string;
}

export interface AgentPromptRequest {
  content: string;
  provider?: string;
  model?: string;
  active_context?: ActiveFileContext | null;
  explicit_context?: ExplicitContextMention[];
}

export interface ActiveFileContext {
  file_path?: string;
  language?: string;
  cursor?: {
    line: number;
    column: number;
  };
  selection?: {
    start_line: number;
    start_column: number;
    end_line: number;
    end_column: number;
    text?: string;
  } | null;
  content_preview?: string;
  updated_at?: string;
}

export interface ExplicitContextMention {
  id: string;
  type: 'file' | 'symbol' | 'endpoint';
  label: string;
  path?: string;
  line?: number;
  source?: 'workspace' | 'semantic';
  content?: string;
}

export interface ContextRetrieveResult {
  type: string;
  path?: string | null;
  source_file?: string | null;
  relevance?: number;
  score?: number;
  summary?: string | null;
  content?: string | null;
  symbols?: Array<{
    type: string;
    name: string;
    line: number;
    file_path?: string | null;
    docstring?: string | null;
    parameters?: string[] | null;
  }>;
}

export interface ContextRetrieveResponse {
  success: boolean;
  context: ContextRetrieveResult[];
  project_info?: Record<string, any> | null;
}

export interface ContextMention extends ExplicitContextMention {
  detail?: string;
  method?: string;
  route?: string;
  score?: number;
  related?: Array<Record<string, any>>;
}

export interface ContextMentionResponse {
  success: boolean;
  mentions: ContextMention[];
  project_info?: Record<string, any> | null;
  indexed_at?: string | null;
}

export interface AgentPart {
  id: string;
  session_id: string;
  type: 'text' | 'tool_call' | 'tool_result' | 'diff' | 'command' | 'permission' | 'summary' | 'error';
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'approved' | 'executed';
  title?: string;
  content?: string;
  payload?: Record<string, any>;
  created_at: string;
  updated_at?: string;
}

export interface AgentSessionState {
  touched_paths?: string[];
  changed_files?: string[];
  latest_diff_part_id?: string;
  latest_command_part_id?: string;
  latest_error?: string;
  repair_attempts?: number;
  max_repair_attempts?: number;
  fallback_summary_used?: boolean;
  current_phase?: string;
}

export interface AgentSessionDiagnosticItem {
  id?: string;
  type?: string;
  status?: string;
  title?: string;
  content?: string;
  event_type?: string;
  message?: string;
  policy_decision?: string;
  risk_level?: string;
  policy_reason?: string;
  changed_files?: string[];
  exit_code?: number;
  failure_summary?: string;
  created_at?: string;
  payload?: Record<string, any>;
}

export interface AgentSessionDiagnostics {
  status?: string;
  current_phase?: string;
  latest_event?: AgentSessionDiagnosticItem | null;
  latest_tool_call?: AgentSessionDiagnosticItem | null;
  latest_tool_result?: AgentSessionDiagnosticItem | null;
  latest_action?: AgentSessionDiagnosticItem | null;
  latest_command?: AgentSessionDiagnosticItem | null;
  latest_summary?: AgentSessionDiagnosticItem | null;
  latest_error?: AgentSessionDiagnosticItem | null;
  recent_events?: AgentSessionDiagnosticItem[];
  stop_reason?: string;
  next_action?: string;
  refresh_safe?: boolean;
}

export interface AgentSessionUiTimelineItem {
  id: string;
  part_id?: string;
  session_id?: string;
  type: AgentPart['type'] | string;
  status?: AgentPart['status'] | string;
  title?: string;
  content?: string;
  tool?: string;
  agent_name?: string;
  agent_role?: string;
  task_id?: string;
  child_session_id?: string;
  async_status?: string;
  child_status?: string;
  has_pending_permission?: boolean;
  pending_permission_part_id?: string | null;
  created_at?: string;
  updated_at?: string;
  payload?: Record<string, any>;
  legacy?: boolean;
}

export interface AgentSessionUiPendingPermissionAction {
  index: number;
  name: string;
  args: Record<string, any>;
  description?: string;
  allowed_decisions: string[];
}

export interface AgentSessionUiPendingPermission {
  part_id: string;
  status?: string;
  title?: string;
  content?: string;
  actions: AgentSessionUiPendingPermissionAction[];
  allowed_decisions?: string[];
  decisions_payload?: Record<string, any>;
}

export interface AgentSessionUiState {
  session_id?: string;
  agent_id?: string;
  status?: string;
  timeline: AgentSessionUiTimelineItem[];
  pending_permission?: AgentSessionUiPendingPermission | null;
  latest?: Record<string, AgentSessionDiagnosticItem | null | undefined>;
  artifacts?: Array<AgentArtifact & { source?: string }>;
  status_text?: {
    current_phase?: string;
    stop_reason?: string;
    next_action?: string;
  };
}

export interface AgentSessionStreamingDiagnostics {
  mode?: 'chat_stream' | 'non_stream' | string;
  status?: string;
  provider?: string;
  model?: string;
  source?: string;
  reason?: string;
  error?: string;
  fallback_to_non_stream?: boolean;
  current_part_id?: string;
  content_length?: number;
  updated_at?: string;
}

export interface AgentLoopGuardSnapshot {
  blocked_reason?: string;
  blocked_reason_code?: string;
  blocked_signature?: string;
  repeat_count?: number;
  threshold?: number;
  tool?: string;
  input_excerpt?: string;
  error_excerpt?: string;
  output_excerpt?: string;
  recovered_at?: string;
}

export interface AgentLoopGuardState extends AgentLoopGuardSnapshot {
  blocked?: boolean;
  family_repeat_count?: number;
  consecutive_failure_count?: number;
  no_progress_repeat_count?: number;
  last_signature?: string;
  last_family_signature?: string;
  last_no_progress_signature?: string;
  recent_failures?: Array<Record<string, unknown>>;
  recent_observations?: Array<Record<string, unknown>>;
  history?: AgentLoopGuardSnapshot[];
  last_block?: AgentLoopGuardSnapshot;
}

export interface AgentSessionPreferences {
  display_title?: string | null;
  pinned: boolean;
  archived: boolean;
  updated_at?: string | null;
}

export interface AgentSessionPreferencesUpdate {
  display_title?: string | null;
  pinned?: boolean | null;
  archived?: boolean | null;
}

export interface AgentSession {
  id: string;
  chat_session_id?: string;
  agent_id: string;
  status:
    | 'idle'
    | 'running'
    | 'waiting_permission'
    | 'waiting_approval'
    | 'verifying'
    | 'repairing'
    | 'needs_manual_review'
    | 'interrupted'
    | 'completed'
    | 'failed';
  title: string;
  project_path?: string;
  workspace_id?: string;
  task_mode?: 'build' | 'train' | 'hybrid';
  provider?: string;
  model?: string;
  metadata?: Record<string, any> & {
    state?: AgentSessionState;
    diagnostics?: AgentSessionDiagnostics;
    streaming_diagnostics?: AgentSessionStreamingDiagnostics;
    ui_state?: AgentSessionUiState;
    loop_guard?: AgentLoopGuardState;
  };
  parts: AgentPart[];
  preferences: AgentSessionPreferences;
  created_at: string;
  updated_at: string;
}

export interface AgentSessionApprovalResponse {
  part: AgentPart;
  session: AgentSession;
}

export type AgentHitlDecision =
  | { type: 'approve' }
  | { type: 'reject'; message?: string }
  | { type: 'respond'; message: string }
  | { type: 'edit'; edited_action: { name: string; args: Record<string, any> } };

export interface AgentArtifact {
  id: string;
  path: string;
  status: string;
  summary: string;
  preview: string;
  source_part_id: string;
}

export interface AgentSessionOverview {
  session: AgentSession;
  recent_events: AgentSessionDiagnosticItem[];
  artifacts: AgentArtifact[];
  diagnostics: AgentSessionDiagnostics;
}

export type AgentAsyncTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface AgentAsyncTask {
  task_id: string;
  parent_session_id: string;
  child_session_id?: string | null;
  previous_child_session_ids: string[];
  agent_name: string;
  status: AgentAsyncTaskStatus;
  input: Record<string, any>;
  result: Record<string, any>;
  error?: string | null;
  restart_count: number;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  last_checked_at?: string | null;
  diagnostics?: Record<string, any>;
  events?: AgentAsyncTaskEvent[];
  duration_ms?: number | null;
  queue_wait_ms?: number | null;
  health_status?: 'ok' | 'waiting' | 'attention' | 'failed' | 'cancelled';
  child_status?: string | null;
  has_pending_permission?: boolean;
  pending_permission_part_id?: string | null;
}

export interface AgentAsyncTaskListResponse {
  tasks: AgentAsyncTask[];
  status_filter: string;
}

export interface AgentAsyncTaskEvent {
  id: string;
  task_id: string;
  parent_session_id: string;
  child_session_id?: string | null;
  event_type: string;
  status?: string | null;
  message: string;
  payload: Record<string, any>;
  created_at: string;
}

export interface AgentAsyncTaskMetrics {
  total: number;
  by_status: Record<string, number>;
  running: number;
  failed: number;
  cancelled: number;
  completed: number;
  attention: number;
  recovery_count: number;
  event_count: number;
  last_event?: AgentAsyncTaskEvent | null;
}

export interface AgentWorkspaceArtifact {
  id: string;
  artifact_type:
    | 'summary'
    | 'finding'
    | 'risk'
    | 'decision'
    | 'question'
    | 'research_note'
    | 'file_change'
    | 'subtask_result'
    | 'command_result'
    | 'run_summary'
    | 'findings'
    | 'risks'
    | 'test_result'
    | string;
  type?: string | null;
  title: string;
  summary: string;
  status?: string;
  source?: {
    kind: string;
    id?: string | null;
    label?: string | null;
  } | null;
  payload: Record<string, any>;
  source_part_id?: string | null;
  source_task_id?: string | null;
  producer_agent?: string | null;
  created_at?: string | null;
}

export interface AgentWorkspaceChangedFile {
  path: string;
  status: string;
  summary: string;
  source_part_id?: string | null;
}

export type AgentWorkspaceNextActionType =
  | 'resolve_permission'
  | 'review_risks'
  | 'run_tests'
  | 'start_explore'
  | 'start_review'
  | 'continue_build'
  | 'inspect_file'
  | 'restart_failed_task';

export interface AgentWorkspaceNextAction {
  id: string;
  action_type: AgentWorkspaceNextActionType;
  title: string;
  summary: string;
  priority: 'high' | 'medium' | 'low';
  source_artifact_id?: string | null;
  source_task_id?: string | null;
  payload: Record<string, any>;
}

export interface AgentWorkspaceRecentEvent {
  id?: string;
  event_type?: string;
  message?: string;
  created_at?: string;
  payload?: Record<string, any>;
}

export interface AgentExecutionTimelineItem {
  id: string;
  type: 'tool_call' | 'tool_result' | 'command' | 'permission' | 'summary' | 'error' | 'recovery';
  title: string;
  status?: string | null;
  summary: string;
  source_part_id: string;
  created_at?: string | null;
  duration_ms?: number | null;
  payload_excerpt: Record<string, any>;
}

export interface AgentApprovalInboxItem {
  id: string;
  scope: 'parent' | 'child';
  session_id: string;
  task_id?: string | null;
  child_session_id?: string | null;
  permission_part_id: string;
  title: string;
  status?: string | null;
  actions_count: number;
  actions: AgentSessionUiPendingPermission['actions'];
  updated_at?: string | null;
}

export interface AgentWorkspaceMount {
  path: string;
  kind: string;
  label: string;
  writable: boolean;
  description: string;
}

export interface AgentWorkspaceSkillSource {
  name: string;
  virtual_path: string;
  priority: number;
  available: boolean;
  enabled?: boolean;
}

export interface AgentExecutionPlan {
  schema_version: 'agent.execution.plan.v1' | string;
  runtime: string;
  backend_mode: string;
  thread_id?: string | null;
  recursion_limit?: number | null;
  checkpointer: boolean;
  state_machine: string;
  plan_id?: string | null;
  session_id?: string | null;
  goal: string;
  status: string;
  current_node_id?: string | null;
  nodes: AgentExecutionPlanNode[];
  edges: AgentExecutionPlanEdge[];
  created_at?: string | null;
  updated_at?: string | null;
  lifecycle: string[];
}

export interface AgentExecutionPlanNode {
  id: string;
  title: string;
  description?: string;
  agent_id?: string;
  kind?: string;
  status: string;
  depends_on?: string[];
  input_contract?: Record<string, any>;
  output_contract?: Record<string, any>;
  retry_policy?: Record<string, any>;
  approval_policy?: Record<string, any>;
  output?: Record<string, any>;
  error?: string | null;
  source_part_id?: string | null;
  source_permission_part_id?: string | null;
  source_event_id?: string | null;
  source_task_id?: string | null;
  tool?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  blocked_reason?: string | null;
  recoverable?: boolean;
  recovery_action?: 'retry_node' | 'resume_node' | 'restart_subagent' | 'manual_review' | string | null;
  recovery_reason?: string | null;
  recovery_attempts?: number;
  last_recovery_at?: string | null;
  recovery_error?: string | null;
}

export interface AgentExecutionPlanEdge {
  from: string;
  to: string;
  type: string;
}

export interface AgentExecutionPlanRecoveryResponse {
  session: AgentSession;
  execution_plan?: AgentExecutionPlan | null;
  workspace: AgentWorkspace;
  node_id: string;
  action: 'retry_node' | 'resume_node' | 'restart_subagent' | 'manual_review' | string;
  started_task_id?: string | null;
}

export interface AgentRuntimePolicy {
  schema_version: 'agent.runtime.policy.v1' | string;
  runtime_kind: string;
  agent_id: string;
  agent_name: string;
  mode: string;
  readonly: boolean;
  workspace_root?: string | null;
  provider?: string | null;
  model?: string | null;
  capabilities: Record<string, boolean>;
  tools: {
    allowed?: string[];
    allow_all_builtin?: boolean;
    async_tools_enabled?: boolean;
    async_tool_names?: string[];
    [key: string]: any;
  };
  output_contract: {
    source?: string;
    format?: string;
    requirements?: string;
    enforced_in_prompt?: boolean;
    [key: string]: any;
  };
  recovery_policy: {
    failure_status?: string | null;
    manual_review_status?: string | null;
    resume_after_permission?: boolean;
    restart_recovery?: boolean;
    records_fallback_summary?: boolean;
    state_machine?: string;
    [key: string]: any;
  };
  handoff_targets: string[];
  async_subagent_targets: string[];
  filesystem_profile: string;
  interrupt_on?: Record<string, any> | null;
  enabled_skill_sources?: string[] | null;
  skill_sources: AgentWorkspaceSkillSource[];
  vfs_mounts: AgentWorkspaceMount[];
  memory_files: string[];
  resource_profile: AgentResourceProfile;
  execution_plan: AgentExecutionPlan;
}

export interface AgentResourceProfile {
  schema_version: 'agent.resource.profile.v1' | string;
  agent: Record<string, any>;
  memory: {
    user_id?: string;
    agent_id?: string;
    org_id?: string;
    namespaces?: Array<{
      scope: string;
      namespace: string;
      mount: string;
      writable: boolean;
    }>;
    files?: string[];
    [key: string]: any;
  };
  skills: {
    enabled_skill_sources?: string[] | null;
    sources?: AgentWorkspaceSkillSource[];
    [key: string]: any;
  };
  mounts: AgentWorkspaceMount[];
}

export interface AgentWorkspaceRuntimeContext {
  workspace_root?: string | null;
  vfs_mounts: AgentWorkspaceMount[];
  skill_sources: AgentWorkspaceSkillSource[];
  memory_files: string[];
  policy?: AgentRuntimePolicy | null;
  resource_profile?: AgentResourceProfile | null;
  execution_plan?: AgentExecutionPlan | null;
}

export interface AgentWorkspace {
  session: AgentSession;
  status_text: {
    current_phase?: string;
    stop_reason?: string;
    next_action?: string;
  };
  timeline: AgentSessionUiTimelineItem[];
  pending_permission?: AgentSessionUiPendingPermission | null;
  plan?: {
    todos: Array<{
      id: string;
      title: string;
      status: 'pending' | 'in_progress' | 'completed' | 'blocked';
      summary?: string;
      owner_agent?: string | null;
      source?: string;
      linked_artifact_id?: string | null;
      linked_task_id?: string | null;
    }>;
    source: string;
    updated_at?: string | null;
  };
  todos?: Array<{
    id: string;
    title: string;
    status: 'pending' | 'in_progress' | 'completed' | 'blocked';
    summary?: string;
    owner_agent?: string | null;
    source?: string;
    linked_artifact_id?: string | null;
    linked_task_id?: string | null;
  }>;
  diagnostics: AgentSessionDiagnostics & Record<string, any>;
  async_tasks: {
    tasks: AgentAsyncTask[];
    metrics: AgentAsyncTaskMetrics;
  };
  artifacts: AgentWorkspaceArtifact[];
  changed_files: AgentWorkspaceChangedFile[];
  next_actions: AgentWorkspaceNextAction[];
  execution_timeline?: AgentExecutionTimelineItem[];
  recent_events: AgentWorkspaceRecentEvent[];
  runtime?: AgentWorkspaceRuntimeContext;
  runtime_policy?: AgentRuntimePolicy | null;
  resource_profile?: AgentResourceProfile | null;
  execution_plan?: AgentExecutionPlan | null;
  vfs_mounts?: AgentWorkspaceMount[];
  skill_sources?: AgentWorkspaceSkillSource[];
}

export interface AgentDiagnosticsReport {
  version: number;
  sessionId: string | null;
  protocolVersion: string;
  unknownEvents: number;
  parseFailures: number;
  reconnects: number;
  recoveryRequested: number;
  recoverySucceeded: number;
  recoveryFailed: number;
  attentionByKind: Record<string, number>;
  updatedAt: string;
}

export interface AgentDiagnosticsSummary {
  sessions: number;
  unknown_events: number;
  parse_failures: number;
  reconnects: number;
  recovery_requested: number;
  recovery_succeeded: number;
  recovery_failed: number;
  recovery_success_rate: number | null;
  updated_at?: string | null;
}

export interface AgentSkillManifest {
  name: string;
  description: string;
  virtual_skill_file?: string | null;
  allowed_tools: string[];
}

export interface AgentSkillSource {
  name: string;
  virtual_path: string;
  priority: number;
  available: boolean;
  enabled_by_default: boolean;
  skills: AgentSkillManifest[];
}

export interface AgentSkillRegistry {
  sources: AgentSkillSource[];
  runtime_policy?: AgentRuntimePolicy | null;
  resource_profile?: AgentResourceProfile | null;
}

export interface AgentMemoryFile {
  id: string;
  path: string;
  relative_path: string;
  scope: string;
  namespace: string;
  content: string;
  writable: boolean;
  version: number;
  updated_at?: string | null;
  metadata: Record<string, any>;
}

export interface AgentSessionEvent {
  id: string;
  session_id: string;
  event_type: string;
  chunk_type?:
    | 'status'
    | 'phase'
    | 'part_start'
    | 'part_delta'
    | 'part_complete'
    | 'part_snapshot'
    | 'tool_call'
    | 'tool_result'
    | 'permission_request'
    | 'action'
    | 'summary'
    | 'error'
    | 'async_task'
    | 'tool'
    | 'event'
    | 'session_snapshot';
  message: string;
  payload: Record<string, any>;
  created_at: string;
  session_status?: AgentSession['status'];
  agent_id?: string;
  phase?: string;
  tool?: string;
  agent_name?: string;
  agent_role?: string;
  task_id?: string;
  child_session_id?: string;
  async_status?: string;
  health_status?: string;
  delta?: string;
  content?: string;
  summary?: string;
  part?: AgentPart | null;
  session_snapshot?: AgentSession;
}

export const getAgents = async (): Promise<AgentInfo[]> => {
  const response = await apiClient.get('/agents');
  return response.data;
};

export const getPrimaryAgents = async (): Promise<AgentInfo[]> => {
  const response = await apiClient.get('/agents/primary');
  return response.data;
};

export const getAgent = async (agentId: string): Promise<AgentInfo> => {
  const response = await apiClient.get(`/agents/${agentId}`);
  return response.data;
};

export const classifyChatAgentIntent = async (
  payload: ChatAgentIntentRequest,
): Promise<ChatAgentIntentResponse> => {
  const response = await apiClient.post('/chat-agent/intent', payload);
  return response.data;
};

export const retrieveProjectContext = async (payload: {
  query: string;
  project_path?: string;
  path?: string;
  top_k?: number;
}): Promise<ContextRetrieveResponse> => {
  const response = await apiClient.post('/context/retrieve', payload, {
    suppressErrorLogging: true,
  } as any);
  return response.data;
};

export const searchContextMentions = async (payload: {
  query?: string;
  project_path?: string;
  path?: string;
  kinds?: Array<'file' | 'symbol' | 'endpoint'>;
  limit?: number;
}): Promise<ContextMentionResponse> => {
  const response = await apiClient.post('/context/mentions', payload, {
    suppressErrorLogging: true,
  } as any);
  return response.data;
};

export const createAgentSession = async (payload: AgentSessionCreate): Promise<AgentSession> => {
  const response = await apiClient.post('/agent-sessions', payload, { timeout: 15000 });
  return response.data;
};

export const getAgentSkills = async (params?: {
  project_path?: string;
  agent_id?: string;
}): Promise<AgentSkillRegistry> => {
  const response = await apiClient.get('/agents/skills', { params });
  return response.data;
};

export const listWorkspaces = async (): Promise<WorkspaceSummary[]> => {
  const response = await apiClient.get('/workspace/workspaces');
  return Array.isArray(response.data) ? response.data : response.data?.workspaces || [];
};

export const createWorkspace = async (payload: WorkspaceCreateRequest): Promise<WorkspaceSummary> => {
  const response = await apiClient.post('/workspace/workspaces', payload);
  return response.data;
};

export const updateWorkspace = async (workspaceId: string, payload: WorkspaceUpdateRequest): Promise<WorkspaceSummary> => {
  const response = await apiClient.put(`/workspace/workspaces/${workspaceId}`, payload);
  return response.data;
};

export const deleteWorkspace = async (workspaceId: string): Promise<void> => {
  await apiClient.delete(`/workspace/workspaces/${workspaceId}`);
};

export const getWorkspaceTree = async (params: {
  workspace_id?: string;
  project_path?: string;
  max_depth?: number;
  limit?: number;
}): Promise<WorkspaceTreeResponse> => {
  const response = await apiClient.get('/workspace/tree', { params });
  return response.data;
};

export const browseFolderBackend = async (initialPath?: string): Promise<{ status: string; path: string | null; message?: string }> => {
  const response = await apiClient.get('/workspace/browse-folder', {
    params: { initial_path: initialPath }
  });
  return response.data;
};

export interface AllowedWorkspaceRoot {
  path: string;
  source: string;
  label?: string;
}

export interface AllowedWorkspaceRootsResponse {
  default_project_path: string;
  roots: AllowedWorkspaceRoot[];
}

export interface WorkspacePathValidation {
  ok: boolean;
  resolved_path: string | null;
  allowed: boolean;
  exists: boolean;
  is_dir: boolean;
  needs_register: boolean;
  message: string | null;
  error_code: 'path_missing' | 'path_not_dir' | 'path_not_allowed' | null;
}

export const getAllowedWorkspaceRoots = async (): Promise<AllowedWorkspaceRootsResponse> => {
  const response = await apiClient.get('/workspace/allowed-roots');
  return response.data;
};

export const validateWorkspacePath = async (path?: string | null): Promise<WorkspacePathValidation> => {
  const response = await apiClient.post('/workspace/validate-path', { path: path ?? null });
  return response.data;
};

/** Prefer Electron native picker; fall back to backend OS dialog. */
export const browseWorkspaceFolder = async (initialPath?: string): Promise<string | null> => {
  const electronApi =
    typeof window !== 'undefined'
      ? (window as Window & { electronAPI?: { selectFolder?: (path?: string) => Promise<string | null> } }).electronAPI
      : undefined;
  if (electronApi?.selectFolder) {
    return electronApi.selectFolder(initialPath);
  }
  const res = await browseFolderBackend(initialPath);
  if (res.status === 'success' && res.path) {
    return res.path;
  }
  if (res.status === 'error') {
    throw new Error(res.message || '文件夹选择失败，请手动输入路径');
  }
  return null;
};

export const readWorkspaceFile = async (params: {
  file_path: string;
  workspace_id?: string;
  project_path?: string;
}): Promise<{ path: string; content: string }> => {
  const response = await apiClient.get('/workspace/read-file', { params });
  return response.data;
};

export const writeWorkspaceFile = async (payload: {
  file_path: string;
  content: string;
  workspace_id?: string;
  project_path?: string;
}): Promise<{ status: string; path: string }> => {
  const response = await apiClient.post('/workspace/write-file', payload);
  return response.data;
};


export const getAgentSession = async (sessionId: string): Promise<AgentSession> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}`);
  return response.data;
};

export const getAgentSessionOverview = async (sessionId: string): Promise<AgentSessionOverview> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/overview`);
  return response.data;
};

export const getAgentWorkspace = async (sessionId: string): Promise<AgentWorkspace> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/workspace`);
  return response.data;
};

export const listAgentSessions = async (limit = 100): Promise<AgentSession[]> => {
  const response = await apiClient.get('/agent-sessions', { params: { limit } });
  return response.data;
};

export const reportAgentDiagnostics = async (
  reports: AgentDiagnosticsReport[],
): Promise<{ accepted: number }> => {
  const response = await apiClient.post('/agent-sessions/diagnostics/batch', { reports });
  return response.data;
};

export const getAgentDiagnosticsSummary = async (): Promise<AgentDiagnosticsSummary> => {
  const response = await apiClient.get('/agent-sessions/diagnostics/summary');
  return response.data;
};

export const listAgentMemoryFiles = async (sessionId: string): Promise<AgentMemoryFile[]> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/memory-files`);
  return response.data;
};

export const readAgentMemoryFile = async (sessionId: string, path: string): Promise<AgentMemoryFile> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/memory-file`, { params: { path } });
  return response.data;
};

export const getArtifactOriginal = async (
  sessionId: string,
  artifactId: string
): Promise<string | null> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/artifacts/${encodeURIComponent(artifactId)}/original`);
  return response.data;
};

export const promptAgentSession = async (
  sessionId: string,
  payload: AgentPromptRequest,
): Promise<AgentSession> => {
  const response = await apiClient.post(`/agent-sessions/${sessionId}/prompt`, payload, { timeout: 15000 });
  return response.data;
};

export const updateAgentSessionPreferences = async (
  sessionId: string,
  update: AgentSessionPreferencesUpdate
): Promise<AgentSession> => {
  const response = await apiClient.patch(`/agent-sessions/${sessionId}/preferences`, update);
  return response.data;
};

export const interruptAgentSession = async (sessionId: string): Promise<AgentSession> => {
  const response = await apiClient.post(`/agent-sessions/${sessionId}/interrupt`);
  return response.data;
};

export const recoverAgentExecutionPlanNode = async (
  sessionId: string,
  nodeId: string,
  payload: { action?: string | null; instruction?: string | null } = {},
): Promise<AgentExecutionPlanRecoveryResponse> => {
  const response = await apiClient.post(
    `/agent-sessions/${sessionId}/execution-plan/nodes/${encodeURIComponent(nodeId)}/recover`,
    payload,
  );
  return response.data;
};

export const startAgentAsyncTask = async (
  sessionId: string,
  payload: { subagent_type: string; description: string },
): Promise<AgentAsyncTask> => {
  const response = await apiClient.post(`/agent-sessions/${sessionId}/async-tasks`, payload);
  return response.data;
};

export const listAgentAsyncTasks = async (
  sessionId: string,
  statusFilter?: string,
): Promise<AgentAsyncTaskListResponse> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/async-tasks`, {
    params: statusFilter && statusFilter !== 'all' ? { status_filter: statusFilter } : undefined,
  });
  return response.data;
};

export const getAgentAsyncTask = async (sessionId: string, taskId: string): Promise<AgentAsyncTask> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/async-tasks/${taskId}`);
  return response.data;
};

export const getAgentAsyncTaskMetrics = async (sessionId: string): Promise<AgentAsyncTaskMetrics> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/async-tasks/metrics`);
  return response.data;
};

export const listAgentAsyncTaskEvents = async (
  sessionId: string,
  taskId?: string,
  limit = 100,
): Promise<AgentAsyncTaskEvent[]> => {
  const suffix = taskId ? `/${taskId}/events` : '/events';
  const response = await apiClient.get(`/agent-sessions/${sessionId}/async-tasks${suffix}`, {
    params: { limit },
  });
  return response.data;
};

export const updateAgentAsyncTask = async (
  sessionId: string,
  taskId: string,
  payload: { description: string },
): Promise<AgentAsyncTask> => {
  const response = await apiClient.patch(`/agent-sessions/${sessionId}/async-tasks/${taskId}`, payload);
  return response.data;
};

export const cancelAgentAsyncTask = async (
  sessionId: string,
  taskId: string,
  payload?: { reason?: string },
): Promise<AgentAsyncTask> => {
  const response = await apiClient.post(`/agent-sessions/${sessionId}/async-tasks/${taskId}/cancel`, payload || {});
  return response.data;
};

export const approveAgentPermission = async (
  permissionId: string,
): Promise<AgentSessionApprovalResponse> => {
  const response = await apiClient.post(`/agent-permissions/${permissionId}/approve`);
  return response.data;
};

export const rejectAgentPermission = async (
  permissionId: string,
): Promise<AgentSessionApprovalResponse> => {
  const response = await apiClient.post(`/agent-permissions/${permissionId}/reject`);
  return response.data;
};

export const decideAgentPermission = async (
  permissionId: string,
  decisions: AgentHitlDecision[],
): Promise<AgentSessionApprovalResponse> => {
  const response = await apiClient.post(`/agent-permissions/${permissionId}/decide`, { decisions });
  return response.data;
};

export const getAgentSessionEvents = async (sessionId: string): Promise<AgentSessionEvent[]> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/events`);
  return response.data;
};

export interface SavedCloudProvider {
  id: string;
  provider: string;
  name: string;
  masked_key?: string;
  interface_format?: string;
  base_url?: string;
  default_model?: string;
  models?: string[];
  streaming_status?: 'untested' | 'supported' | 'unsupported' | 'failed' | string;
  streaming_supported?: boolean | null;
  streaming_tested_at?: string | null;
  streaming_error?: string;
  streaming_chunks?: number | null;
  streaming_model?: string;
}

export const getSavedCloudProviders = async () => {
  const response = await apiClient.get('/cloud/api-keys');
  return response.data;
};

export const getSavedCloudProviderData = async (provider: string) => {
  const response = await apiClient.get(`/cloud/api-keys/${provider}/data`);
  return response.data;
};

export const testCloudProviderStream = async (
  provider: string,
  params?: { base_url?: string; group_id?: string; version?: string },
) => {
  const response = await apiClient.post(`/cloud/test/${provider}/stream`, null, { params });
  return response.data;
};

// Device APIs
export const getDeviceInfo = async () => {
  const response = await apiClient.get('/device/info');
  return response.data;
};

export const getDeviceVRAM = async () => {
  const response = await apiClient.get('/device/vram');
  return response.data;
};

export const getDeviceMemory = async () => {
  const response = await apiClient.get('/device/memory');
  return response.data;
};

// Model APIs
export const getModelList = async () => {
  const response = await apiClient.get('/models');
  return response.data;
};

export const downloadModel = async (modelId: string, options?: { quantize?: number }) => {
  const response = await apiClient.post('/models/download', { model_name: modelId, ...options });
  return response.data;
};

export const deleteModel = async (modelId: string) => {
  const response = await apiClient.delete(`/models/${modelId}`);
  return response.data;
};

export const getModelDetail = async (modelId: string) => {
  const response = await apiClient.get(`/models/${modelId}`);
  return response.data;
};

// Import model from ModelScope.
export const importModelFromModelScope = async (modelName: string, modelscopePath?: string) => {
  const response = await apiClient.post('/model-center/import-modelscope', {
    model_name: modelName,
    modelscope_path: modelscopePath,
  });
  return response.data;
};

// Search models (ModelScope / HuggingFace)
export const searchModels = async (
  query: string,
  limit: number = 20,
  source: string = 'modelscope',
) => {
  const response = await apiClient.post('/model-center/search', {
    query,
    limit,
    source,
  });
  return response.data;
};

// Download model from ModelScope.
export const downloadModelFromModelScope = async (repoId: string, revision: string = 'master') => {
  const response = await apiClient.post('/model-center/download', {
    repo_id: repoId,
    revision,
    source: 'modelscope',
  });
  return response.data;
};

// Download model from Hugging Face.
export const downloadModelFromHuggingFace = async (repoId: string, revision: string = 'main') => {
  const response = await apiClient.post('/model-center/download', {
    repo_id: repoId,
    revision,
    source: 'huggingface',
  });
  return response.data;
};

// Get model download progress.
export const getDownloadProgress = async (taskId: string) => {
  const response = await apiClient.get(`/model-center/download/${taskId}`);
  return response.data;
};

// Get model suggestions.
export const getModelSuggestions = async () => {
  const url = '/model-center/suggestions';
  const cacheKey = url;
  const cached = getCacheMap.get(cacheKey);
  
  if (cached && Date.now() - cached.timestamp < GET_CACHE_TTL && cached.promise) {
    return cached.promise;
  }
  
  const promise = apiClient.get(url).then(res => responseData(res));
  getCacheMap.set(cacheKey, { timestamp: Date.now(), data: null, promise });
  return promise;
};

const responseData = (res: any) => res.data;

export const extractApiErrorMessage = (error: any, fallback = '请求失败'): string => {
  const data = error?.response?.data;
  const candidates = [
    data?.error?.message,
    data?.detail?.message,
    data?.detail,
    data?.message,
    error?.message,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate.trim();
    }
  }
  return fallback;
};

// Get local model list.
export const getLocalModels = async () => {
  const response = await apiClient.get('/model-center/local');
  return response.data;
};

// Delete local model.
export const deleteLocalModel = async (modelId: string) => {
  const response = await apiClient.delete(`/model-center/local/${modelId}`);
  return response.data;
};

// Get model source config
export const getModelSource = async () => {
  const response = await apiClient.get('/model-center/source');
  return response.data;
};

// Set model source
export const setModelSource = async (source: string) => {
  const response = await apiClient.post('/model-center/source', null, { params: { source } });
  return response.data;
};

// Check network status
export const checkNetworkStatus = async () => {
  const response = await apiClient.get('/model-center/network/status');
  return response.data;
};

// Dataset management
export const getDatasetList = async () => {
  const response = await apiClient.get('/datasets');
  return response.data;
};

export const uploadDataset = async (
  file: File,
  name?: string,
  description?: string,
  onUploadProgress?: (percent: number) => void,
) => {
  const formData = new FormData();
  formData.append('file', file);
  if (name) formData.append('name', name);
  if (description) formData.append('description', description);
  const response = await apiClient.post('/datasets/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onUploadProgress
      ? (e) => {
          if (e.total) onUploadProgress(Math.round((e.loaded / e.total) * 100));
        }
      : undefined,
  });
  return response.data;
};

export const deleteDataset = async (datasetId: string) => {
  const response = await apiClient.delete(`/datasets/${datasetId}`);
  return response.data;
};

export const getDatasetDetail = async (datasetId: string) => {
  const response = await apiClient.get(`/datasets/${datasetId}`);
  return response.data;
};

export const previewDataset = async (datasetId: string, limit: number = 10) => {
  const response = await apiClient.get(`/datasets/${datasetId}/preview`, { params: { limit } });
  return response.data;
};

export const getDatasetStatistics = async (datasetId: string) => {
  const response = await apiClient.get(`/datasets/${datasetId}/statistics`);
  return response.data;
};

export const analyzeDataset = async (datasetId: string, targetGoal?: string) => {
  const response = await apiClient.post('/datasets/analyze', {
    dataset_id: datasetId,
    target_goal: targetGoal,
  });
  return response.data;
};

export const transformDataset = async (
  datasetId: string,
  payload: { target_format?: string; task_goal?: string; output_name?: string },
) => {
  const response = await apiClient.post(`/datasets/${datasetId}/transform`, payload);
  return response.data;
};

export const splitDataset = async (
  datasetId: string,
  payload: {
    train_ratio?: number;
    validation_ratio?: number;
    test_ratio?: number;
    seed?: number;
  } = {},
) => {
  const response = await apiClient.post(`/datasets/${datasetId}/split`, payload);
  return response.data;
};

// Training APIs
export const startTraining = async (
  config: any,
  options?: { applyRecommendedConfig?: boolean },
) => {
  const response = await apiClient.post('/training/start', config, {
    params: {
      apply_recommended_config: options?.applyRecommendedConfig ?? false,
    },
  });
  return response.data;
};

// P2-2: SWIFT training support
export const startSwiftTraining = async (config: any) => {
  const response = await apiClient.post('/training/start-swift', config);
  return response.data;
};

export const stopTraining = async () => {
  const response = await apiClient.post('/training/stop');
  return response.data;
};

export const checkTrainingResources = async (params: {
  method?: string;
  modelSize?: string;
  requiredVram?: number;
}) => {
  const response = await apiClient.post('/training/check-resources', null, {
    params: {
      method: params.method ?? 'qlora',
      model_size: params.modelSize ?? '7B',
      required_vram: params.requiredVram ?? 6.0,
    },
  });
  return response.data;
};

export const checkTrainingPreflight = async (config: any) => {
  const response = await apiClient.post('/training/preflight', config);
  return response.data;
};

export const getTrainingProgress = async () => {
  const response = await apiClient.get('/training/progress');
  return response.data;
};

export const subscribeTrainingProgress = (
  onProgress: (progress: any) => void,
  onError?: (error: Error) => void,
  retryConfig?: Partial<RetryConfig>,
) => {
  let eventSource: EventSource | null = null;
  let retryCount = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let isManualClose = false;
  const config = { ...defaultRetryConfig, ...retryConfig };

  const connect = () => {
    eventSource = new EventSource(`${API_BASE_URL}/training/progress/stream`);

    eventSource.onmessage = (event) => {
      try {
        const progress = JSON.parse(event.data);
        onProgress(progress);
        retryCount = 0;
      } catch (error) {
        console.error('Failed to parse progress:', error);
      }
    };

    eventSource.onerror = () => {
      if (isManualClose) return;

      eventSource?.close();
      eventSource = null;

      if (retryCount < config.maxRetries) {
        const backoffDelay = calculateBackoff(retryCount, config.baseDelay, config.maxDelay);
        console.warn(
          `SSE disconnected, retrying in ${Math.round(backoffDelay)}ms (${retryCount + 1}/${config.maxRetries})`,
        );
        retryCount++;
        retryTimer = setTimeout(connect, backoffDelay);
      } else {
        if (onError) {
          onError(new Error('SSE connection error: max retries reached'));
        }
      }
    };
  };

  connect();

  return () => {
    isManualClose = true;
    if (retryTimer) {
      clearTimeout(retryTimer);
    }
    eventSource?.close();
  };
};

export const subscribeTrainingLogs = (
  taskId: string,
  onLine: (line: string) => void,
  onError?: (error: Error) => void,
  history: number = 50,
) => {
  let eventSource: EventSource | null = null;
  let retryCount = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let isManualClose = false;
  const maxRetries = 5;
  const baseDelay = 2000;
  let suppressHistory = false;

  const connect = () => {
    const url = suppressHistory
      ? `${API_BASE_URL}/training/logs/stream/${encodeURIComponent(taskId)}?history=0`
      : `${API_BASE_URL}/training/logs/stream/${encodeURIComponent(taskId)}?history=${history}`;
    eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      if (!event.data) return;
      try {
        const data = JSON.parse(event.data);
        if (Array.isArray(data.lines)) {
          data.lines.forEach((line: unknown) => onLine(String(line)));
        } else {
          const line = data.line ?? data.message ?? data.content;
          if (line !== undefined && line !== null) onLine(String(line));
        }
        retryCount = 0;
      } catch {
        onLine(event.data);
        retryCount = 0;
      }
    };

    eventSource.onerror = () => {
      if (isManualClose) return;
      eventSource?.close();
      eventSource = null;

      if (retryCount < maxRetries) {
        const delay = Math.min(baseDelay * Math.pow(2, retryCount), 30000);
        retryCount++;
        suppressHistory = true;
        retryTimer = setTimeout(connect, delay);
      } else {
        if (onError) onError(new Error('Log stream disconnected: max retries reached'));
      }
    };
  };

  connect();

  return () => {
    isManualClose = true;
    if (retryTimer) clearTimeout(retryTimer);
    eventSource?.close();
  };
};

export interface TrainingEventV2 {
  event_id: string;
  version: 'v2';
  ts: string;
  task_id: string;
  phase: 'queued' | 'loading' | 'running' | 'stopping' | 'stopped' | 'completed' | 'failed';
  kind: string;
  payload: Record<string, any>;
  sequence: number;
}

export const subscribeTrainingEventsV2 = (
  options: {
    taskId?: string;
    lastEventId?: string;
    heartbeatTimeoutMs?: number;
    retryConfig?: Partial<RetryConfig>;
  },
  onEvent: (event: TrainingEventV2) => void,
  onError?: (error: Error) => void,
) => {
  let eventSource: EventSource | null = null;
  let ws: WebSocket | null = null;
  let wsPingTimer: ReturnType<typeof setInterval> | null = null;
  let retryCount = 0;
  let wsRetryCount = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let isManualClose = false;
  let usingWsFallback = false;
  let lastEventId = options.lastEventId || '';
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  const heartbeatTimeoutMs = options.heartbeatTimeoutMs ?? 45000;
  const config = { ...defaultRetryConfig, ...(options.retryConfig || {}) };

  const closeWs = () => {
    const current = ws;
    ws = null;
    if (wsPingTimer) {
      clearInterval(wsPingTimer);
      wsPingTimer = null;
    }
    if (current) {
      current.onclose = null;
      current.onerror = null;
      current.onmessage = null;
      current.onopen = null;
      current.close();
    }
  };

  const refreshHeartbeatTimeout = () => {
    if (heartbeatTimer) clearTimeout(heartbeatTimer);
    heartbeatTimer = setTimeout(() => {
      if (usingWsFallback) {
        closeWs();
      } else {
        eventSource?.close();
        eventSource = null;
      }
      if (isManualClose) return;
      if (usingWsFallback) {
        startWsFallback();
      } else {
        connect();
      }
    }, heartbeatTimeoutMs);
  };

  const handleParsedEvent = (event: TrainingEventV2) => {
    onEvent(event);
    lastEventId = event.event_id;
    retryCount = 0;
    wsRetryCount = 0;
    refreshHeartbeatTimeout();
  };

  const startWsFallback = () => {
    if (isManualClose) return;
    usingWsFallback = true;
    eventSource?.close();
    eventSource = null;

    const taskId = options.taskId || 'all';
    const url = new URL(API_BASE_URL);
    const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const params = new URLSearchParams();
    if (lastEventId) params.set('last_event_id', lastEventId);
    const qs = params.toString();
    const wsUrl = `${wsProtocol}//${url.host}/training/v2/ws/${encodeURIComponent(taskId)}${qs ? `?${qs}` : ''}`;
    ws = new WebSocket(wsUrl);
    refreshHeartbeatTimeout();

    ws.onopen = () => {
      wsRetryCount = 0;
      if (wsPingTimer) clearInterval(wsPingTimer);
      wsPingTimer = setInterval(() => {
        try {
          ws?.send('ping');
        } catch (_e) {
          // noop
        }
      }, 10000);
    };

    ws.onmessage = (messageEvent) => {
      try {
        const parsed = JSON.parse(messageEvent.data);
        if (parsed?.type === 'pong') {
          refreshHeartbeatTimeout();
          return;
        }
        handleParsedEvent(parsed as TrainingEventV2);
      } catch (error) {
        console.error('Failed to parse WS fallback training event', error);
      }
    };

    ws.onclose = () => {
      closeWs();
      if (isManualClose) return;
      if (wsRetryCount < config.maxRetries) {
        const backoffDelay = calculateBackoff(wsRetryCount, config.baseDelay, config.maxDelay);
        wsRetryCount += 1;
        retryTimer = setTimeout(startWsFallback, backoffDelay);
      } else if (onError) {
        onError(new Error('V2 WS fallback disconnected: max retries reached'));
      }
    };

    ws.onerror = () => {
      closeWs();
    };
  };

  const connect = () => {
    usingWsFallback = false;
    closeWs();
    const params = new URLSearchParams();
    if (options.taskId) params.set('task_id', options.taskId);
    if (lastEventId) params.set('last_event_id', lastEventId);
    const qs = params.toString();
    eventSource = new EventSource(`${API_BASE_URL}/training/v2/events/stream${qs ? `?${qs}` : ''}`);
    refreshHeartbeatTimeout();

    eventSource.onmessage = (messageEvent) => {
      try {
        const event: TrainingEventV2 = JSON.parse(messageEvent.data);
        handleParsedEvent(event);
      } catch (error) {
        console.error('Failed to parse v2 training event', error);
      }
    };

    eventSource.addEventListener('heartbeat', () => {
      refreshHeartbeatTimeout();
    });

    eventSource.onerror = () => {
      if (isManualClose) return;
      eventSource?.close();
      eventSource = null;

      if (retryCount < config.maxRetries) {
        const backoffDelay = calculateBackoff(retryCount, config.baseDelay, config.maxDelay);
        retryCount += 1;
        retryTimer = setTimeout(connect, backoffDelay);
      } else {
        startWsFallback();
      }
    };
  };

  connect();

  return () => {
    isManualClose = true;
    if (retryTimer) clearTimeout(retryTimer);
    if (heartbeatTimer) clearTimeout(heartbeatTimer);
    eventSource?.close();
    closeWs();
  };
};

export const getTrainingOverviewV2 = async () => {
  const response = await apiClient.get('/training/v2/overview');
  return response.data;
};

export const getTrainingTaskMetricsV2 = async (
  taskId: string,
  cursor: number = 0,
  limit: number = 200,
) => {
  const response = await apiClient.get(`/training/v2/tasks/${taskId}/metrics`, {
    params: { cursor, limit },
  });
  return response.data;
};

export const getTrainingHistory = async () => {
  const response = await apiClient.get('/training/history');
  return response.data;
};

export const getTrainingCheckpoints = async (trainingId: string) => {
  const response = await apiClient.get(`/training/checkpoints/${trainingId}`);
  return response.data;
};

export const cleanupTrainingCheckpoints = async (trainingId: string) => {
  const response = await apiClient.delete(`/training/checkpoints/${trainingId}/cleanup`);
  return response.data;
};

export const compareTrainingCheckpoints = async (checkpoints: any[]) => {
  const response = await apiClient.post('/training/checkpoints/compare', { checkpoints });
  return response.data;
};

export const getTrainingRecoveryOptions = async (limit: number = 6) => {
  const response = await apiClient.get('/training/recovery/options', {
    params: { limit },
  });
  return response.data;
};

export const getTrainingFailureAnalytics = async () => {
  const response = await apiClient.get('/training/failure/analytics');
  return response.data;
};
// Inference APIs
export const resumeTraining = async (trainingId: string, checkpoint: string) => {
  const response = await apiClient.post(`/training/resume/${trainingId}/${checkpoint}`);
  return response.data;
};

// Inference service.
export const inference = async (config: {
  modelId: string;
  prompt: string;
  maxTokens?: number;
  temperature?: number;
  backend?: string;
  loraAdapter?: string;
}) => {
  const response = await apiClient.post('/inference/generate', {
    model: config.modelId,
    prompt: config.prompt,
    lora_adapter: config.loraAdapter || undefined,
    options: {
      max_tokens: config.maxTokens,
      temperature: config.temperature,
      backend: config.backend,
      lora_adapter: config.loraAdapter || undefined,
    },
  });
  return response.data;
};

export const streamInference = async (
  config: {
    modelId: string;
    prompt: string;
    maxTokens?: number;
    temperature?: number;
    backend?: string;
    loraAdapter?: string;
  },
  onChunk: (text: string) => void,
  onStats?: (stats: any) => void,
  signal?: AbortSignal,
  retryConfig?: Partial<RetryConfig>,
) => {
  const retryConf = { ...defaultRetryConfig, ...retryConfig };
  let lastError: Error | null = null;

  const parseSSEEvent = (eventStr: string): { eventType: string; data: string } | null => {
    const lines = eventStr.split('\n');
    let eventType = 'message';
    let dataLine = '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        dataLine = line.slice(6);
      }
    }

    return dataLine ? { eventType, data: dataLine } : null;
  };

  const attemptStream = async (): Promise<void> => {
    const controller = new AbortController();
    const connectionKey = `stream:${config.modelId}:${Date.now()}`;
    connectionPool.acquire(connectionKey, 'inference');

    if (signal) {
      signal.addEventListener('abort', () => {
        controller.abort();
        connectionPool.release(connectionKey);
      });
    }

    const response = await fetch(`${API_BASE_URL}/inference/generate/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'omit', // Standard for cross-origin stream if not needed
      body: JSON.stringify({
        model: config.modelId,
        prompt: config.prompt,
        backend: config.backend,
        lora_adapter: config.loraAdapter || undefined,
        options: {
          max_tokens: config.maxTokens,
          temperature: config.temperature,
          backend: config.backend,
          lora_adapter: config.loraAdapter || undefined,
        },
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      connectionPool.release(connectionKey);
      const error = await response.text();
      throw new Error(error || 'Inference failed');
    }

    const reader = response.body?.getReader();
    if (!reader) {
      connectionPool.release(connectionKey);
      throw new Error('No reader available');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      let done = false;
      const streamStartTime = Date.now();
      const STREAM_READ_TIMEOUT = 60000;
      let lastYieldTime = performance.now();

      let flushPending = false;
      let frameId: number | null = null;
      let flushTimeoutId: ReturnType<typeof setTimeout> | null = null;
      let lastFlushTime = 0;
      let chunkBuffer = '';

      const flushUpdate = () => {
        if (chunkBuffer) {
          onChunk(chunkBuffer);
          chunkBuffer = '';
        }
        flushPending = false;
        lastFlushTime = Date.now();
      };

      while (!done) {
        if (Date.now() - streamStartTime > STREAM_READ_TIMEOUT) {
          throw new Error('Stream read timed out');
        }

        const readResult = await reader.read();
        done = readResult.done;
        if (done) break;

        const text = decoder.decode(readResult.value, { stream: true });
        buffer += text;

        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const event of events) {
          if (!event.trim()) continue;

          const parsed = parseSSEEvent(event);
          if (!parsed) continue;

          try {
            const data = JSON.parse(parsed.data);

            if (parsed.eventType === 'error' || data.error) {
              throw new Error(data.error || 'Stream error');
            }

            if (data.content) {
              chunkBuffer += data.content;
              
              if (!flushPending) {
                flushPending = true;
                const now = Date.now();
                const timeSinceLastFlush = now - lastFlushTime;
                const throttleMs = 32;
                
                if (timeSinceLastFlush >= throttleMs) {
                  frameId = requestAnimationFrame(flushUpdate);
                } else {
                  flushTimeoutId = setTimeout(() => {
                    frameId = requestAnimationFrame(flushUpdate);
                  }, throttleMs - timeSinceLastFlush);
                }
              }
            }

            if (data.done) {
              if (data.stats && onStats) {
                onStats(data.stats);
              }
            }
          } catch (e) {
            if (e instanceof Error && e.message !== 'Stream error') {
              console.error('Parse SSE error:', e, 'Raw:', parsed.data);
            } else {
              throw e;
            }
          }
        }

        if (performance.now() - lastYieldTime > 16) {
          await new Promise((resolve) => setTimeout(resolve, 0));
          lastYieldTime = performance.now();
        }
      }
      
      if (flushTimeoutId) clearTimeout(flushTimeoutId);
      if (frameId) cancelAnimationFrame(frameId);
      flushUpdate();
    } finally {
      connectionPool.release(connectionKey);
    }
  };

  for (let attempt = 0; attempt < retryConf.maxRetries; attempt++) {
    try {
      await attemptStream();
      return;
    } catch (error: any) {
      lastError = error;

      if (error.name === 'AbortError') {
        throw error;
      }

      if (!isRetryableError(error)) {
        throw error;
      }

      if (attempt < retryConf.maxRetries - 1) {
        const backoffDelay = calculateBackoff(attempt, retryConf.baseDelay, retryConf.maxDelay);
        console.warn(
          `Streaming inference failed, retrying in ${Math.round(backoffDelay)}ms (${attempt + 1}/${retryConf.maxRetries})`,
          error.message,
        );
        await delay(backoffDelay);
      }
    }
  }

  throw lastError;
};

export const chatInference = async (
  modelId: string,
  messages: Array<{ role: string; content: string }>,
  options?: {
    maxTokens?: number;
    temperature?: number;
    backend?: string;
    loraAdapter?: string;
  },
) => {
  const response = await apiClient.post('/inference/chat', {
    model_id: modelId,
    messages,
    options: {
      max_tokens: options?.maxTokens,
      temperature: options?.temperature,
      backend: options?.backend,
      lora_adapter: options?.loraAdapter,
    },
  });
  return response.data;
};

export const generateTitleCloud = async (
  content: string,
  config: {
    provider: string;
    model: string;
    apiKey?: string;
    keyId?: string;
    groupId?: string;
    baseUrl?: string;
  }
) => {
  const response = await apiClient.post('/cloud/chat', {
    provider: config.provider,
    model: config.model,
    api_key: config.apiKey,
    key_id: config.keyId,
    group_id: config.groupId,
    base_url: config.baseUrl,
    messages: [{ role: 'user', content: `你是一个专业的对话摘要助手。请根据以下对话内容，生成一个极其简短、专业且具代表性的对话标题。

约束条件：
- 长度控制在 2-6 个词或 10 个汉字以内。
- 优先提取对话的核心技术点、问题意图或目标。
- 直接返回标题，严禁包含任何前缀（如“标题：”）、后缀、引号或标点符号。
- 如果对话过于简短无法判断主题，请返回“新对话”。

对话内容：
${content}` }],
    temperature: 0.5,
    max_tokens: 20
  });
  return (response.data.content || response.data.message?.content)
    ?.replace(/<think>[\s\S]*?<\/think>\s*/gi, '')
    .trim()
    .replace(/^(标题|Title|Summary)[:：]\s*/i, '')
    .replace(/^["'「『]|["'」』]$/g, '')
    .substring(0, 15);
};

export const generateTitleLocal = async (
  modelId: string,
  backend: string,
  content: string
) => {
  const response = await apiClient.post('/inference/chat', {
    model_id: modelId,
    messages: [{ role: 'user', content: `你是一个专业的对话摘要助手。请根据以下对话内容，生成一个极其简短、专业且具代表性的对话标题。

约束条件：
- 长度控制在 2-6 个词或 10 个汉字以内。
- 优先提取对话的核心技术点、问题意图或目标。
- 直接返回标题，严禁包含任何前缀（如“标题：”）、后缀、引号或标点符号。
- 如果对话过于简短无法判断主题，请返回“新对话”。

对话内容：
${content}` }],
    options: {
      backend,
      temperature: 0.5,
      max_tokens: 20
    }
  });
  return (response.data.content || response.data.message?.content)
    ?.replace(/<think>[\s\S]*?<\/think>\s*/gi, '')
    .trim()
    .replace(/^(标题|Title|Summary)[:：]\s*/i, '')
    .replace(/^["'「『]|["'」』]$/g, '')
    .substring(0, 15);
};

export const getBackends = async () => {
  const response = await apiClient.get('/inference/backends');
  return response.data;
};

export const switchBackend = async (backend: string) => {
  const response = await apiClient.post('/inference/backends/switch', { backend });
  return response.data;
};

export const getOllamaStatus = async (config?: AxiosRequestConfig) => {
  const response = await apiClient.get('/inference/ollama/status', config);
  return response.data;
};

export const createEvaluationRun = async (payload: any) => {
  const response = await apiClient.post('/evaluation/runs', payload);
  return response.data;
};

export const getEvaluationRuns = async () => {
  const response = await apiClient.get('/evaluation/runs');
  return response.data;
};

export const getEvaluationRun = async (runId: string) => {
  const response = await apiClient.get(`/evaluation/runs/${runId}`);
  return response.data;
};

export const scoreEvaluationCase = async (runId: string, payload: any) => {
  const response = await apiClient.post(`/evaluation/runs/${runId}/score`, payload);
  return response.data;
};

export const createDeploymentPackage = async (payload: any) => {
  const response = await apiClient.post('/deployment/packages', payload);
  return response.data;
};

export const listDeploymentPackages = async (limit: number = 20) => {
  const response = await apiClient.get('/deployment/packages', { params: { limit } });
  return response.data;
};

export const getDeploymentPackage = async (packageId: string) => {
  const response = await apiClient.get(`/deployment/packages/${packageId}`);
  return response.data;
};

export const deleteDeploymentPackage = async (packageId: string) => {
  const response = await apiClient.delete(`/deployment/packages/${packageId}`);
  return response.data;
};

export const getInferenceModels = async () => {
  const response = await apiClient.get('/inference/models');
  const data = response.data;
  if (Array.isArray(data)) {
    return data;
  }
  if (Array.isArray(data?.models)) {
    return data.models;
  }
  return [];
};

export interface RuntimeBootstrapPayload {
  schema_version: 'runtime.bootstrap.v1';
  generated_at: string;
  observed: {
    backend_status: 'connected' | 'disconnected' | 'checking';
    inference: {
      backends: Array<{
        id: string;
        name: string;
        available: boolean;
        description?: string;
      }>;
      current_backend: string;
      huggingface_models: Array<{
        id: string;
        name: string;
        size?: number | null;
        source?: string | null;
      }>;
      ollama: {
        available: boolean;
        running: boolean;
        base_url?: string | null;
        models: Array<{
          id: string;
          name: string;
          size?: number | null;
          source?: string | null;
        }>;
      };
    };
    knowledge: {
      collections: Array<{
        id: string;
        name: string;
        count: number;
      }>;
      embedder_status: {
        loaded: boolean;
        model_name?: string;
        dimension?: number;
        error?: string;
      };
    };
    training: {
      is_training?: boolean;
      progress?: {
        status?:
          | 'idle'
          | 'loading'
          | 'training'
          | 'running'
          | 'stopping'
          | 'stopped'
          | 'completed'
          | 'failed';
        message?: string;
      } | null;
    };
    storage?: Record<string, any>;
  };
  derived: {
    runtime_status: 'ready' | 'degraded' | 'offline';
    warnings: string[];
    available_model_count: number;
    storage_status?: string;
  };
}

export const getRuntimeBootstrap = async (): Promise<RuntimeBootstrapPayload> => {
  const response = await apiClient.get('/runtime/bootstrap');
  return response.data;
};

export const getPerformanceStats = async (modelId?: string) => {
  const params = modelId ? `?model_id=${modelId}` : '';
  const response = await apiClient.get(`/inference/performance${params}`);
  return response.data;
};

export const getPerformanceRecommendations = async () => {
  const response = await apiClient.get('/inference/performance/recommendations');
  return response.data;
};

export const getInferenceCacheStatus = async () => {
  const response = await apiClient.get('/inference/cache/status');
  return response.data;
};

export const clearPerformanceHistory = async () => {
  const response = await apiClient.post('/inference/performance/clear');
  return response.data;
};

// Chat history APIs.
export const getChatHistory = async () => {
  const response = await apiClient.get('/chat/sessions');
  return response.data.sessions || [];
};

export const createChatSession = async (title: string, modelId: string) => {
  const response = await apiClient.post('/chat/sessions', {
    title,
    metadata: { model_id: modelId },
  });
  return response.data;
};

export const getChatSession = async (sessionId: string) => {
  const response = await apiClient.get(`/chat/sessions/${sessionId}`);
  return response.data;
};

export const deleteChatSession = async (sessionId: string) => {
  const response = await apiClient.delete(`/chat/sessions/${sessionId}`);
  return response.data;
};

export const addChatMessages = async (
  sessionId: string,
  messages: Array<{ id: string; role: string; content: string; timestamp: string }>,
) => {
  const createdMessages = [];
  for (const item of messages) {
    const response = await apiClient.post(`/chat/sessions/${sessionId}/messages`, {
      role: item.role,
      content: item.content,
      metadata:
        item.id || item.timestamp
          ? {
              legacy_message_id: item.id,
              legacy_timestamp: item.timestamp,
            }
          : {},
    });
    createdMessages.push(response.data);
  }
  return { messages: createdMessages, count: createdMessages.length };
};

export interface MergeLoraParams {
  adapter_path?: string;
  adapterPath?: string;
  training_id?: string;
  trainingId?: string;
  output_name?: string;
  outputName?: string;
  [key: string]: any;
}

export const mergeLora = async (
  modelId: string,
  outputNameOrParams: string | MergeLoraParams,
  maybeParams: MergeLoraParams = {},
) => {
  const rawPayload =
    typeof outputNameOrParams === 'string'
      ? { ...maybeParams, output_name: outputNameOrParams }
      : outputNameOrParams;
  const payload = {
    ...rawPayload,
    adapter_path: rawPayload.adapter_path ?? rawPayload.adapterPath,
    training_id: rawPayload.training_id ?? rawPayload.trainingId,
    output_name: rawPayload.output_name ?? rawPayload.outputName,
  };
  const response = await apiClient.post(`/models/${modelId}/merge`, payload);
  return response.data;
};

// Health check
export const checkBackendHealth = async () => {
  try {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 5000);
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      signal: controller.signal,
    });
    window.clearTimeout(timeoutId);
    if (!response.ok) return false;
    processOfflineQueue();
    return true;
  } catch {
    return false;
  }
};

export const startHealthCheck = (
  onStatusChange: (isHealthy: boolean) => void
): (() => void) => {
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let httpFallbackTimer: ReturnType<typeof setInterval> | null = null;
  let isClosed = false;

  const startHttpFallback = () => {
    if (httpFallbackTimer) return;
    httpFallbackTimer = setInterval(async () => {
      const isHealthy = await checkBackendHealth();
      if (!isClosed) {
        onStatusChange(isHealthy);
      }
    }, 5000);
  };

  const stopHttpFallback = () => {
    if (httpFallbackTimer) {
      clearInterval(httpFallbackTimer);
      httpFallbackTimer = null;
    }
  };

  const connectWS = () => {
    if (isClosed) return;
    
    // 使用 gateway/ws 检测长连接存活状态
    const wsUrl = API_BASE_URL.replace(/^http/i, 'ws') + '/gateway/ws';
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      onStatusChange(true);
      processOfflineQueue();
      stopHttpFallback(); // WebSocket连接成功，停止HTTP轮询
    };

    ws.onmessage = () => {
      // onopen 已上报 connected，此处仅处理离线队列，不重复触发状态变更
      processOfflineQueue();
    };

    ws.onclose = () => {
      ws = null;
      if (!isClosed) {
        // WebSocket 断开，启动 HTTP 轮询作为 fallback，并在后台尝试重连
        startHttpFallback();
        reconnectTimer = setTimeout(connectWS, 5000);
      }
    };

    ws.onerror = () => {
      // onerror 会紧跟着触发 onclose
    };
  };

  // 初始启动时，先做一次 HTTP 检查，然后尝试 WS
  checkBackendHealth().then(isHealthy => {
    if (!isClosed) onStatusChange(isHealthy);
  });
  connectWS();

  return () => {
    isClosed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    stopHttpFallback();
    if (ws) {
      const currentSocket = ws;
      ws = null;
      currentSocket.onmessage = null;
      currentSocket.onerror = null;
      currentSocket.onclose = null;
      if (currentSocket.readyState === WebSocket.OPEN) {
        currentSocket.close();
      } else if (currentSocket.readyState === WebSocket.CONNECTING) {
        currentSocket.onopen = () => currentSocket.close();
      }
    }
  };
};

export const retryEvaluationRun = async (runId: string) => {
  const response = await apiClient.post(`/evaluation/runs/${runId}/retry`);
  return response.data;
};

export const checkDeploymentHealth = async (packageId: string) => {
  const response = await apiClient.post(`/deployment/packages/${packageId}/health`);
  return response.data;
};

export const activateDeploymentPackage = async (packageId: string) => {
  const response = await apiClient.post(`/deployment/packages/${packageId}/activate`);
  return response.data;
};

export const deactivateDeploymentPackage = async (packageId: string) => {
  const response = await apiClient.post(`/deployment/packages/${packageId}/deactivate`);
  return response.data;
};

export const rollbackDeploymentPackage = async (packageId: string) => {
  const response = await apiClient.post(`/deployment/packages/${packageId}/rollback`);
  return response.data;
};

// ==================== CUA API ====================

export const cua = {
  getScreenInfo: () => apiClient.get('/cua/screen/info'),
  takeScreenshot: (params: {
    monitor?: number;
    region?: { x: number; y: number; width: number; height: number };
    format?: string;
    quality?: number;
  }) => apiClient.post('/cua/screenshot', params),
  getMousePosition: () => apiClient.get('/cua/mouse/position'),
  mouseClick: (params: { x: number; y: number; button?: string; clicks?: number }) =>
    apiClient.post('/cua/mouse/click', params),
  mouseMove: (params: { x: number; y: number; duration?: number }) =>
    apiClient.post('/cua/mouse/move', params),
  mouseDrag: (params: {
    start_x: number;
    start_y: number;
    end_x: number;
    end_y: number;
    duration?: number;
    button?: string;
  }) => apiClient.post('/cua/mouse/drag', params),
  mouseScroll: (params: { clicks: number; x?: number; y?: number }) =>
    apiClient.post('/cua/mouse/scroll', params),
  keyboardType: (params: { text: string; interval?: number }) =>
    apiClient.post('/cua/keyboard/type', params),
  keyboardPress: (params: { key: string }) => apiClient.post('/cua/keyboard/press', params),
  keyboardHotkey: (params: { keys: string[] }) => apiClient.post('/cua/keyboard/hotkey', params),
  listWindows: () => apiClient.get('/cua/window/list'),
  getActiveWindow: () => apiClient.get('/cua/window/active'),
  activateWindow: (windowId: string) =>
    apiClient.post('/cua/window/activate', { window_id: windowId }),
  closeWindow: (windowId: string) => apiClient.post('/cua/window/close', { window_id: windowId }),
  ocrRecognize: (params: { image_base64?: string; region?: object; lang?: string }) =>
    apiClient.post('/cua/ocr', params),
  findText: (params: { text: string; lang?: string; fuzzy?: boolean }) =>
    apiClient.post('/cua/ocr/find-text', params),
  recordAction: (action: 'start' | 'stop' | 'pause' | 'resume') =>
    apiClient.post('/cua/record/action', { action }),
  getRecordedActions: () => apiClient.get('/cua/record/actions'),
  playbackActions: (params: { actions?: object[]; filepath?: string; speed?: number }) =>
    apiClient.post('/cua/record/play', params),
  getSafetyStatus: () => apiClient.get('/cua/safety/status'),
  setPermissionLevel: (level: string) =>
    apiClient.post('/cua/safety/permission', null, { params: { level } }),
  getAuditLogs: (limit?: number) => apiClient.get('/cua/safety/logs', { params: { limit } }),
};

// ==================== MCP API ====================

export const mcp = {
  listTools: () => apiClient.get('/mcp/tools'),
  callTool: (params: { tool_name: string; arguments: object }) =>
    apiClient.post('/mcp/call', params),
  listServers: () => apiClient.get('/mcp/servers'),
  addServer: (params: {
    name: string;
    transport: string;
    command?: string;
    args?: string[];
    url?: string;
  }) => apiClient.post('/mcp/servers', params),
  removeServer: (name: string) => apiClient.delete(`/mcp/servers/${name}`),
  getServerStatus: (name: string) => apiClient.get(`/mcp/servers/${name}/status`),
  reconnectServer: (name: string) => apiClient.post(`/mcp/servers/${name}/reconnect`),
  getServerTools: (name: string) => apiClient.get(`/mcp/servers/${name}/tools`),
  getOverallStatus: () => apiClient.get('/mcp/status'),
};

// ==================== Inference Engine APIs ====================

// ==================== Inference Engine APIs (Refactor) ====================

export interface InferenceEngine {
  name: string;
  backend: string;
  available: boolean;
  supports_streaming: boolean;
  supports_chat: boolean;
}

export interface GenerateRequest {
  model_id: string;
  prompt: string;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  top_k?: number;
  repetition_penalty?: number;
  backend?: string;
}

export interface ChatGenerateRequest {
  model_id: string;
  messages: Array<{ role: string; content: string }>;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  system_prompt?: string;
  backend?: string;
}

export interface InferenceResponse {
  text: string;
  tokens_generated: number;
  processing_time_ms: number;
  model_id: string;
  backend: string;
  finish_reason: string;
}

export const listInferenceEngines = async (): Promise<{
  engines: InferenceEngine[];
  default_engine: string;
}> => {
  const response = await apiClient.get('/inference-engine/engines');
  return response.data;
};

export const getInferenceEngineInfo = async (engineName: string) => {
  const response = await apiClient.get(`/inference-engine/engines/${engineName}`);
  return response.data;
};

export const generateText = async (request: GenerateRequest): Promise<InferenceResponse> => {
  const response = await apiClient.post('/inference-engine/generate', request);
  return response.data;
};

export const generateChat = async (request: ChatGenerateRequest): Promise<InferenceResponse> => {
  const response = await apiClient.post('/inference-engine/chat', request);
  return response.data;
};

export const streamGenerate = async (
  request: GenerateRequest,
  onChunk: (content: string) => void,
  onComplete?: () => void,
  signal?: AbortSignal,
) => {
  const response = await fetch(`${API_BASE_URL}/inference-engine/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  });

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No reader available');

  const decoder = new TextDecoder();

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value);
    const lines = text.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          if (data.content) {
            onChunk(data.content);
          }
          if (data.done && onComplete) {
            onComplete();
          }
        } catch (e) {
          // Ignore parse errors
        }
      }
    }
  }
};

export const loadInferenceModel = async (modelId: string, backend?: string) => {
  const params = backend ? `?backend=${backend}` : '';
  const response = await apiClient.post(`/inference-engine/models/${modelId}/load${params}`);
  return response.data;
};

export const unloadInferenceModel = async (modelId: string, backend?: string) => {
  const params = backend ? `?backend=${backend}` : '';
  const response = await apiClient.delete(`/inference-engine/models/${modelId}${params}`);
  return response.data;
};

export const getInferenceModelInfo = async (modelId: string, backend?: string) => {
  const params = backend ? `?backend=${backend}` : '';
  const response = await apiClient.get(`/inference-engine/models/${modelId}/info${params}`);
  return response.data;
};

export const getInferenceEngineStats = async () => {
  const response = await apiClient.get('/inference-engine/stats');
  return response.data;
};

/**
 * Extract a human-readable error message from an API error response.
 * Falls back to the provided defaultMessage (or a generic one) if no detail is available.
 */
export function getApiErrorMessage(error: unknown, defaultMessage = '操作失败'): string {
  if (!error) return defaultMessage;
  // Axios error with a response body
  const axiosError = error as any;
  if (axiosError?.response?.data) {
    const data = axiosError.response.data;
    if (typeof data === 'string') return data;
    if (data.detail) {
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail)) {
        // FastAPI validation error format
        return data.detail.map((d: any) => d.msg ?? JSON.stringify(d)).join('; ');
      }
      return JSON.stringify(data.detail);
    }
    if (data.message) return data.message;
    if (data.error) return data.error;
  }
  if (axiosError?.message) return axiosError.message;
  if (error instanceof Error) return error.message;
  return defaultMessage;
}

// ==================== Model Runtime Center ====================

export interface ModelRuntimeReadiness {
  state: 'ready' | 'blocked' | 'pending';
  label: string;
  message: string;
  fix_action: string | null;
}

export interface ModelRuntimeModel {
  id: string;
  name: string;
  backend: string;
  source: string;
  path: string | null;
  size: number;
  size_label: string;
  capabilities: string[];
  readiness: ModelRuntimeReadiness;
  recommended_for: string[];
  metadata: Record<string, unknown>;
}

export interface ModelRuntimeRecommendation {
  repo_id: string;
  name: string;
  description: string;
  size: string;
  source: string;
  category: string;
  fit: string;
  why: string;
}

export interface ModelRuntimeEnvironment {
  models_dir?: string;
  model_source?: string;
  ollama_base_url?: string;
  hardware_profile?: {
    profile?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface ModelRuntimeDiagnostic {
  kind: string;
  severity?: 'info' | 'warning' | 'error' | string;
  message: string;
  [key: string]: unknown;
}

export interface ModelRuntimeOverview {
  schema_version: string;
  generated_at: string;
  summary: {
    state: string;
    headline: string;
    total_models: number;
    agent_ready_models: number;
    local_ready_models: number;
    ollama_available: boolean;
  };
  active_selection: {
    backend: string | null;
    model_id: string | null;
    scope: string;
  };
  agent: {
    ready: boolean;
    provider: string | null;
    model: string | null;
    model_string: string | null;
    message: string;
  };
  backends: unknown[];
  local_models: ModelRuntimeModel[];
  recommended_models: ModelRuntimeRecommendation[];
  quick_actions: Array<{
    id: string;
    label: string;
    kind: string;
    target: string;
  }>;
  environment: ModelRuntimeEnvironment;
  diagnostics: ModelRuntimeDiagnostic[];
}

export const getModelRuntimeOverview = async (): Promise<ModelRuntimeOverview> => {
  const response = await apiClient.get('/model-runtime/overview');
  return response.data;
};

export const setModelRuntimeSelection = async (payload: {
  backend: 'huggingface' | 'ollama' | 'llama-cpp';
  model_id?: string | null;
  scope?: 'global' | 'agent';
}): Promise<unknown> => {
  const response = await apiClient.post('/model-runtime/selection', payload);
  return response.data;
};

export default apiClient;
