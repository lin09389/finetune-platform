/**
 * API service layer.
 * Handles connection reuse, request cancellation, and automatic retry logic.
 */
import axios, { AxiosInstance } from 'axios';

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
console.log('[API] Base URL:', API_BASE_URL);

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
    console.log(`[API] Processing offline queue: ${offlineQueue.length} requests`);
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
    '/digital-team/templates',
    '/model-center/suggestions',
    '/model-center/source',
    '/workflows/templates'
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

      // 处理离线缓冲
      if (error.message === 'Network Error' || error.code === 'ECONNABORTED' || (error.response && error.response.status >= 500)) {
         // 只缓冲写操作
         const url = String(config?.url || '');
         const shouldQueue = config && ['post', 'put', 'patch', 'delete'].includes((config.method || '').toLowerCase())
           && !url.includes('/agent-sessions/');
         if (shouldQueue) {
            console.log(`[API] Network error detected, queuing request: ${config.method} ${config.url}`);
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

// Digital Team APIs
export interface DigitalTeamProjectCreate {
  title: string;
  goal: string;
  template_id?: string;
  project_path?: string;
  provider?: string;
  model?: string;
  approval_mode?: string;
}

export const getDigitalTeamTemplates = async () => {
  const url = '/digital-team/templates';
  const cacheKey = url;
  const cached = getCacheMap.get(cacheKey);
  
  if (cached && Date.now() - cached.timestamp < GET_CACHE_TTL && cached.promise) {
    return cached.promise;
  }
  
  const promise = apiClient.get(url).then(res => responseData(res));
  getCacheMap.set(cacheKey, { timestamp: Date.now(), data: null, promise });
  return promise;
};

export const createDigitalTeamProject = async (payload: DigitalTeamProjectCreate) => {
  const response = await apiClient.post('/digital-team/projects', payload);
  return response.data;
};

export const getDigitalTeamProjects = async () => {
  const response = await apiClient.get('/digital-team/projects');
  return response.data;
};

export const getDigitalTeamProject = async (projectId: string) => {
  const response = await apiClient.get(`/digital-team/projects/${projectId}`);
  return response.data;
};

export const runDigitalTeamProject = async (projectId: string) => {
  const response = await apiClient.post(`/digital-team/projects/${projectId}/run`);
  return response.data;
};

export const approveDigitalTeamTask = async (
  taskId: string,
  payload: { approved?: boolean; comment?: string } = {},
) => {
  const response = await apiClient.post(`/digital-team/tasks/${taskId}/approve`, {
    approved: payload.approved ?? true,
    comment: payload.comment,
  });
  return response.data;
};

export const retryDigitalTeamTask = async (taskId: string) => {
  const response = await apiClient.post(`/digital-team/tasks/${taskId}/retry`);
  return response.data;
};

export const getDigitalTeamTimeline = async (projectId: string) => {
  const response = await apiClient.get(`/digital-team/projects/${projectId}/timeline`);
  return response.data;
};

export const getDigitalTeamArtifacts = async (projectId: string) => {
  const response = await apiClient.get(`/digital-team/projects/${projectId}/artifacts`);
  return response.data;
};

// Workflow APIs
export interface WorkflowCreate {
  title: string;
  goal: string;
  template_id?: string;
  project_path?: string;
  chat_session_id?: string;
  include_project_context?: boolean;
  include_chat_context?: boolean;
  include_memory?: boolean;
  max_context_chars?: number;
  provider?: string;
  model?: string;
  autonomy_mode?: 'safe_auto' | 'confirm_all' | 'read_only';
  approval_mode?: string;
}

export interface WorkflowAgentConfig {
  agent_id: string;
  name: string;
  description?: string;
  system_prompt: string;
  output_requirements?: string;
}

export interface WorkflowStepConfig {
  step_key: string;
  agent_id: string;
  title: string;
  description?: string;
  artifact_type: string;
  requires_approval: boolean;
  sort_order?: number;
}

export interface WorkflowTemplatePayload {
  id: string;
  name: string;
  description?: string;
  default_provider?: string;
  default_model?: string;
  default_approval_mode?: string;
  is_enabled?: boolean;
  agents: WorkflowAgentConfig[];
  steps: WorkflowStepConfig[];
}

export interface WorkflowStep {
  id: string;
  step_id: string;
  workflow_id: string;
  step_key: string;
  agent_id: string;
  legacy_role: string;
  title: string;
  description: string;
  status: string;
  requires_approval: boolean;
  input_data?: Record<string, any>;
  output_data?: Record<string, any>;
  output?: Record<string, any>;
  error?: string;
}

export interface Workflow {
  id: string;
  workflow_id: string;
  title: string;
  goal: string;
  template_id: string;
  legacy_template_id: string;
  project_path?: string;
  provider: string;
  model?: string;
  approval_mode: string;
  status: string;
  current_stage?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  metadata?: Record<string, any>;
  active_agent_id?: string;
  steps: WorkflowStep[];
}

export interface WorkflowContextProfile {
  workflow_id: string;
  project_path?: string;
  chat_session_id?: string;
  include_project_context: boolean;
  include_chat_context: boolean;
  include_memory: boolean;
  max_context_chars: number;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface WorkflowContextSnapshot {
  id: string;
  workflow_id: string;
  step_id?: string;
  step_key?: string;
  context_type: string;
  content: string;
  sources: Array<Record<string, any>>;
  char_count: number;
  created_at: string;
}

export interface WorkflowMemoryEntry {
  id: string;
  workflow_id: string;
  source_step_id?: string;
  memory_type: string;
  memory_key: string;
  memory_value: Record<string, any>;
  content: string;
  confidence: number;
  status: string;
  external_memory_id?: string;
  created_at: string;
  updated_at: string;
  reverted_at?: string;
}

export interface WorkflowStepLog {
  id: string;
  workflow_id: string;
  step_id?: string;
  step_key?: string;
  agent_id?: string;
  status: string;
  provider?: string;
  model?: string;
  input_summary?: string;
  output_summary?: string;
  error?: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface WorkflowToolCall {
  id: string;
  workflow_id: string;
  step_id?: string;
  agent_id?: string;
  tool_name: string;
  arguments: Record<string, any>;
  status: 'running' | 'completed' | 'failed' | string;
  result_summary?: string;
  result_payload?: Record<string, any>;
  permission_decision?: 'allow' | 'deny' | 'ask';
  blocked_reason?: string;
  replay_of_call_id?: string;
  trace_id?: string;
  raw_model_output?: string;
  sanitized_model_output?: string;
  parse_error?: string;
  protocol_repair_attempted?: boolean;
  error?: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  created_at: string;
}

export interface WorkflowActionExecution {
  id: string;
  action_id: string;
  workflow_id: string;
  status: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number;
  duration_ms?: number;
  error?: string;
  failure_summary?: string;
  created_at: string;
}

export interface WorkflowAction {
  id: string;
  workflow_id: string;
  step_id?: string;
  action_type: 'patch' | 'command' | string;
  title: string;
  description?: string;
  payload: Record<string, any>;
  status: string;
  created_by?: string;
  execution_mode?: 'auto' | 'approval_required' | string;
  policy_decision?: 'auto' | 'approval_required' | 'blocked' | string;
  policy_reason?: string;
  risk_level?: 'low' | 'medium' | 'high' | string;
  auto_executed_at?: string;
  execution_state?: string;
  changed_files?: string[];
  applied_hunks?: number;
  patch_summaries?: Array<Record<string, any>>;
  failure_summary?: string;
  approved_at?: string;
  rejected_at?: string;
  executed_at?: string;
  created_at: string;
  updated_at: string;
  executions?: WorkflowActionExecution[];
}

export interface WorkflowObservability {
  workflow_id: string;
  status: string;
  current_stage?: string;
  active_agent_id?: string;
  subagent_runs?: Array<Record<string, any>>;
  auto_execution_policy?: Record<string, any>;
  blocked_state?: Record<string, any> | null;
  step_logs: WorkflowStepLog[];
  tool_calls?: WorkflowToolCall[];
  actions: WorkflowAction[];
  recent_events: Array<Record<string, any>>;
}

export interface ChatAgentRunCreate {
  chat_session_id?: string;
  message_id?: string;
  content: string;
  template_id?: string;
  provider?: string;
  model?: string;
  agent_id?: string;
  project_path?: string;
  autonomy_mode?: 'safe_auto' | 'confirm_all' | 'read_only';
  force_agent?: boolean;
}

export interface ChatAgentIntentRequest {
  content: string;
  provider?: string;
  model?: string;
  agent_id?: string;
  template_id?: string;
  chat_session_id?: string;
  routing_mode?: 'auto' | 'chat' | 'agent';
}

export interface ChatAgentIntentResponse {
  mode: 'chat' | 'agent';
  confidence: number;
  reason: string;
  source: 'local_rule' | 'cloud' | 'fallback' | 'manual';
  suggested_agent_id?: string;
  suggested_template_id?: string;
}

  export interface ChatAgentAcceptanceReport {
    result: 'passed' | 'partial' | 'blocked' | 'failed';
    summary: string;
    completed_items?: string[];
    changed_files?: string[];
    commands_run?: string[];
    verification_result?: string;
    blocking_reason?: string;
    next_action?: string;
  }

  export interface ChatAgentRun {
  id: string;
  mode: 'chat' | 'agent';
  chat_session_id?: string;
  trigger_message_id?: string;
  workflow_id?: string;
  status: string;
  intent_type?: string;
  summary?: string;
  final_summary?: string;
  execution_state?: string;
  execution_state_message?: string;
  recoverable?: boolean;
  model_protocol_status?: 'ok' | 'repaired' | 'fallback_summary' | 'needs_manual_review' | string;
  last_model_output_preview?: string;
  parse_repair_count?: number;
    fallback_summary_used?: boolean;
    acceptance_report?: ChatAgentAcceptanceReport;
    acceptance_report_source?: 'model' | 'fallback' | string;
    acceptance_report_raw?: string;
    details_url?: string;
  active_agent_id?: string;
  subagent_runs?: Array<Record<string, any>>;
  auto_execution_policy?: Record<string, any>;
  blocked_state?: Record<string, any> | null;
  workflow?: Workflow;
  observability?: WorkflowObservability;
  latest_event?: Record<string, any>;
  latest_tool_call?: WorkflowToolCall;
  latest_action?: WorkflowAction;
}

export interface AgentInfo {
  id: string;
  name: string;
  description?: string;
  mode: 'primary' | 'subagent' | 'all' | string;
  system_prompt?: string;
  default_provider?: string;
  default_model?: string;
  max_iterations?: number;
  tools?: string[];
  permission_rules?: Array<Record<string, any>>;
  handoff_targets?: string[];
  hidden?: boolean;
}

export interface ChatAgentRunEvent {
  event_type: string;
  run_id: string;
  workflow_id?: string;
  message: string;
  payload: Record<string, any>;
}

export interface AgentSessionCreate {
  chat_session_id?: string;
  agent_id?: string;
  title?: string;
  project_path?: string;
  provider?: string;
  model?: string;
  autonomy_mode?: 'safe_auto' | 'confirm_all' | 'read_only';
}

export interface AgentPromptRequest {
  content: string;
  provider?: string;
  model?: string;
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
    | 'completed'
    | 'failed';
  title: string;
  project_path?: string;
  provider?: string;
  model?: string;
  metadata?: Record<string, any> & {
    state?: AgentSessionState;
    diagnostics?: AgentSessionDiagnostics;
    streaming_diagnostics?: AgentSessionStreamingDiagnostics;
  };
  parts: AgentPart[];
  created_at: string;
  updated_at: string;
}

export interface AgentSessionApprovalResponse {
  part: AgentPart;
  session: AgentSession;
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
  delta?: string;
  content?: string;
  summary?: string;
  part?: AgentPart | null;
  session_snapshot?: AgentSession;
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  legacy_template_id: string;
  is_builtin: boolean;
  is_enabled: boolean;
  default_provider?: string;
  default_model?: string;
  default_approval_mode?: string;
  agents: Array<WorkflowAgentConfig & { id?: string }>;
  steps: Array<{
    key: string;
    step_key: string;
    agent_id: string;
    legacy_role: string;
    title: string;
    description: string;
    artifact_type: string;
    requires_approval: boolean;
    sort_order?: number;
  }>;
}

export const getWorkflowTemplates = async () => {
  const url = '/workflows/templates';
  const cacheKey = url;
  const cached = getCacheMap.get(cacheKey);
  
  if (cached && Date.now() - cached.timestamp < GET_CACHE_TTL && cached.promise) {
    return cached.promise;
  }

  const promise = apiClient.get(url).then(res => responseData(res));
  getCacheMap.set(cacheKey, { timestamp: Date.now(), data: null, promise });
  return promise;
};

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

export const createWorkflowTemplate = async (payload: WorkflowTemplatePayload) => {
  const response = await apiClient.post('/workflows/templates', payload);
  return response.data;
};

export const updateWorkflowTemplate = async (
  templateId: string,
  payload: Omit<WorkflowTemplatePayload, 'id'>,
) => {
  const response = await apiClient.put(`/workflows/templates/${templateId}`, payload);
  return response.data;
};

export const deleteWorkflowTemplate = async (templateId: string) => {
  const response = await apiClient.delete(`/workflows/templates/${templateId}`);
  return response.data;
};

export const createWorkflow = async (payload: WorkflowCreate) => {
  const response = await apiClient.post('/workflows', payload);
  return response.data;
};

export const getWorkflows = async () => {
  const response = await apiClient.get('/workflows');
  return response.data;
};

export const getWorkflow = async (workflowId: string) => {
  const response = await apiClient.get(`/workflows/${workflowId}`);
  return response.data;
};

export const runWorkflow = async (workflowId: string) => {
  const response = await apiClient.post(`/workflows/${workflowId}/run`);
  return response.data;
};

export const approveWorkflowStep = async (
  stepId: string,
  payload: { approved?: boolean; comment?: string } = {},
) => {
  const response = await apiClient.post(`/workflow-steps/${stepId}/approve`, {
    approved: payload.approved ?? true,
    comment: payload.comment,
  });
  return response.data;
};

export const retryWorkflowStep = async (stepId: string) => {
  const response = await apiClient.post(`/workflow-steps/${stepId}/retry`);
  return response.data;
};

export const getWorkflowTimeline = async (workflowId: string) => {
  const response = await apiClient.get(`/workflows/${workflowId}/timeline`);
  return response.data;
};

export const getWorkflowArtifacts = async (workflowId: string) => {
  const response = await apiClient.get(`/workflows/${workflowId}/artifacts`);
  return response.data;
};

export const getWorkflowObservability = async (
  workflowId: string,
): Promise<WorkflowObservability> => {
  const response = await apiClient.get(`/workflows/${workflowId}/observability`);
  return response.data;
};

export const getWorkflowStepLogs = async (workflowId: string): Promise<WorkflowStepLog[]> => {
  const response = await apiClient.get(`/workflows/${workflowId}/step-logs`);
  return response.data;
};

export const getWorkflowToolCalls = async (workflowId: string): Promise<WorkflowToolCall[]> => {
  const response = await apiClient.get(`/workflows/${workflowId}/tool-calls`);
  return response.data;
};

export const getWorkflowActions = async (workflowId: string): Promise<WorkflowAction[]> => {
  const response = await apiClient.get(`/workflows/${workflowId}/actions`);
  return response.data;
};

export const approveWorkflowAction = async (actionId: string): Promise<WorkflowAction> => {
  const response = await apiClient.post(`/workflow-actions/${actionId}/approve`);
  return response.data;
};

export const rejectWorkflowAction = async (actionId: string): Promise<WorkflowAction> => {
  const response = await apiClient.post(`/workflow-actions/${actionId}/reject`);
  return response.data;
};

export const executeWorkflowAction = async (actionId: string): Promise<WorkflowAction> => {
  const response = await apiClient.post(`/workflow-actions/${actionId}/execute`);
  return response.data;
};

export const createChatAgentRun = async (payload: ChatAgentRunCreate): Promise<ChatAgentRun> => {
  const response = await apiClient.post('/chat-agent/runs', payload);
  return response.data;
};

export const classifyChatAgentIntent = async (
  payload: ChatAgentIntentRequest,
): Promise<ChatAgentIntentResponse> => {
  const response = await apiClient.post('/chat-agent/intent', payload);
  return response.data;
};

export const getChatAgentRun = async (runId: string): Promise<ChatAgentRun> => {
  const response = await apiClient.get(`/chat-agent/runs/${runId}`);
  return response.data;
};

export const getChatAgentToolCalls = async (runId: string): Promise<WorkflowToolCall[]> => {
  const response = await apiClient.get(`/chat-agent/runs/${runId}/tool-calls`);
  return response.data;
};

export const runChatAgentRun = async (runId: string): Promise<ChatAgentRun> => {
  const response = await apiClient.post(`/chat-agent/runs/${runId}/run`);
  return response.data;
};

export const approveChatAgentStep = async (
  stepId: string,
  payload: { approved?: boolean; comment?: string } = {},
): Promise<ChatAgentRun> => {
  const response = await apiClient.post(`/chat-agent/steps/${stepId}/approve`, {
    approved: payload.approved ?? true,
    comment: payload.comment,
  });
  return response.data;
};

export const approveChatAgentAction = async (actionId: string): Promise<WorkflowAction> => {
  const response = await apiClient.post(`/chat-agent/actions/${actionId}/approve`);
  return response.data;
};

export const rejectChatAgentAction = async (actionId: string): Promise<WorkflowAction> => {
  const response = await apiClient.post(`/chat-agent/actions/${actionId}/reject`);
  return response.data;
};

export const executeChatAgentAction = async (actionId: string): Promise<WorkflowAction> => {
  const response = await apiClient.post(`/chat-agent/actions/${actionId}/execute`);
  return response.data;
};

export const createAgentSession = async (payload: AgentSessionCreate): Promise<AgentSession> => {
  const response = await apiClient.post('/agent-sessions', payload);
  return response.data;
};

export const getAgentSession = async (sessionId: string): Promise<AgentSession> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}`);
  return response.data;
};

export const promptAgentSession = async (
  sessionId: string,
  payload: AgentPromptRequest,
): Promise<AgentSession> => {
  const response = await apiClient.post(`/agent-sessions/${sessionId}/prompt`, payload);
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

export const approveAgentAction = async (actionId: string): Promise<AgentSessionApprovalResponse> => {
  const response = await apiClient.post(`/agent-actions/${actionId}/approve`);
  return response.data;
};

export const rejectAgentAction = async (actionId: string): Promise<AgentSessionApprovalResponse> => {
  const response = await apiClient.post(`/agent-actions/${actionId}/reject`);
  return response.data;
};

export const executeAgentAction = async (actionId: string): Promise<AgentSessionApprovalResponse> => {
  const response = await apiClient.post(`/agent-actions/${actionId}/execute`);
  return response.data;
};

export const getAgentSessionEvents = async (sessionId: string): Promise<AgentSessionEvent[]> => {
  const response = await apiClient.get(`/agent-sessions/${sessionId}/events`);
  return response.data;
};

export const getWorkflowContext = async (workflowId: string): Promise<WorkflowContextProfile> => {
  const response = await apiClient.get(`/workflows/${workflowId}/context`);
  return response.data;
};

export const updateWorkflowContext = async (
  workflowId: string,
  payload: Omit<WorkflowContextProfile, 'workflow_id' | 'created_at' | 'updated_at'>,
): Promise<WorkflowContextProfile> => {
  const response = await apiClient.put(`/workflows/${workflowId}/context`, payload);
  return response.data;
};

export const getWorkflowContextSnapshots = async (
  workflowId: string,
): Promise<WorkflowContextSnapshot[]> => {
  const response = await apiClient.get(`/workflows/${workflowId}/context/snapshots`);
  return response.data;
};

export const getWorkflowMemory = async (workflowId: string): Promise<WorkflowMemoryEntry[]> => {
  const response = await apiClient.get(`/workflows/${workflowId}/memory`);
  return response.data;
};

export const revertWorkflowMemory = async (memoryId: string): Promise<WorkflowMemoryEntry> => {
  const response = await apiClient.post(`/workflow-memory/${memoryId}/revert`);
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

export const uploadDataset = async (file: File, name?: string, description?: string) => {
  const formData = new FormData();
  formData.append('file', file);
  if (name) formData.append('name', name);
  if (description) formData.append('description', description);
  const response = await apiClient.post('/datasets/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
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
}) => {
  const response = await apiClient.post('/inference/generate', config);
  return response.data;
};

export const streamInference = async (
  config: {
    modelId: string;
    prompt: string;
    maxTokens?: number;
    temperature?: number;
    backend?: string;
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
        options: {
          max_tokens: config.maxTokens,
          temperature: config.temperature,
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
    let chunkCount = 0;

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
              chunkCount++;
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
              console.log(`Streaming inference completed with ${chunkCount} chunks`);
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
        console.log('Streaming inference was cancelled');
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
  options?: { maxTokens?: number; temperature?: number },
) => {
  const response = await apiClient.post('/inference/chat', {
    model_id: modelId,
    messages,
    ...options,
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

export const getOllamaStatus = async () => {
  const response = await apiClient.get('/inference/ollama/status');
  return response.data;
};

export const createEvaluationRun = async (payload: any) => {
  const response = await apiClient.post('/evaluation/runs', payload);
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
    const response = await apiClient.get('/health', { suppressErrorLogging: true } as any);
    if (response.status === 200) {
      processOfflineQueue();
      return true;
    }
    return false;
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
      onStatusChange(true);
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
    if (ws) ws.close();
  };
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

export default apiClient;
