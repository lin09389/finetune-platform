/**
 * API 服务配置
 * 支持连接复用、请求取消、错误自动重试
 */
import axios, { AxiosInstance } from 'axios';

// 获取 API 基础 URL
const getApiBaseUrl = () => {
  if (typeof window !== 'undefined' && (window as any).electronAPI) {
    return (window as any).electronAPI.getBackendUrlSync?.() || 'http://127.0.0.1:8000';
  }
  return ((import.meta as any).env?.VITE_API_URL || 'http://127.0.0.1:8000') as string;
};

// 导出 API_BASE_URL 供其他模块使用
export const API_BASE_URL = getApiBaseUrl();

// ==================== 连接池管理 ====================

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
    // 只从池中移除，不 abort（请求已完成）
    this.pool.delete(key);
  }

  abortByKey(key: string): void {
    const entry = this.pool.get(key);
    if (entry) {
      entry.controller.abort();
      this.pool.delete(key);
    }
  }

  abortByType(requestType: string): void {
    const keysToRemove: string[] = [];
    this.pool.forEach((entry, key) => {
      if (entry.requestType === requestType) {
        entry.controller.abort();
        keysToRemove.push(key);
      }
    });
    keysToRemove.forEach(key => this.pool.delete(key));
  }

  abortAll(): void {
    this.pool.forEach(entry => {
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

    keysToRemove.forEach(key => this.pool.delete(key));
  }

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

// ==================== 错误重试机制 ====================

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
  return new Promise(resolve => setTimeout(resolve, ms));
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
    retryableError =>
      errorMessage.includes(retryableError.toLowerCase()) ||
      errorCode.includes(retryableError.toLowerCase())
  );
}

async function fetchWithRetry<T>(
  fetchFn: () => Promise<T>,
  config: Partial<RetryConfig> = {}
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
        console.warn(`请求失败，${backoffDelay}ms 后重试 (第 ${attempt + 1}/${retryConfig.maxRetries} 次):`, error.message);
        await delay(backoffDelay);
      }
    }
  }

  throw lastError;
}

// ==================== Axios 实例配置 ====================

const createAxiosInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: API_BASE_URL,
    timeout: 300000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  instance.interceptors.request.use(
    (config) => {
      const key = connectionPool.generateKey(config.url || '', config.method || 'get');
      const controller = connectionPool.acquire(key, 'axios');
      config.signal = controller.signal;
      (config as any)._connectionKey = key;
      return config;
    },
    (error) => {
      return Promise.reject(error);
    }
  );

  instance.interceptors.response.use(
    (response) => {
      const key = (response.config as any)?._connectionKey;
      if (key) {
        connectionPool.release(key);
      }
      return response;
    },
    (error) => {
      const key = (error.config as any)?._connectionKey;
      if (key) {
        connectionPool.release(key);
      }

      if (error.response) {
        console.error('API Error:', error.response.data);
      } else if (error.request) {
        console.error('Network Error:', error.request);
      } else {
        console.error('Error:', error.message);
      }
      return Promise.reject(error);
    }
  );

  return instance;
};

export const apiClient = createAxiosInstance();

// ==================== 请求取消管理 ====================

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

// 设备管理
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

// 模型管理
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

// 导入 ModelScope 模型
export const importModelFromModelScope = async (modelName: string, modelscopePath?: string) => {
  const response = await apiClient.post('/model-center/import-modelscope', {
    model_name: modelName,
    modelscope_path: modelscopePath
  });
  return response.data;
};

// 搜索模型（支持 ModelScope 和 HuggingFace）
export const searchModels = async (query: string, limit: number = 20, source: string = 'modelscope') => {
  const response = await apiClient.post('/model-center/search', {
    query,
    limit,
    source
  });
  return response.data;
};

// 从 ModelScope 下载模型
export const downloadModelFromModelScope = async (repoId: string, revision: string = 'master') => {
  const response = await apiClient.post('/model-center/download', {
    repo_id: repoId,
    revision,
    source: 'modelscope'
  });
  return response.data;
};

// 从 HuggingFace 下载模型
export const downloadModelFromHuggingFace = async (repoId: string, revision: string = 'main') => {
  const response = await apiClient.post('/model-center/download', {
    repo_id: repoId,
    revision,
    source: 'huggingface'
  });
  return response.data;
};

// 获取模型下载进度
export const getDownloadProgress = async (taskId: string) => {
  const response = await apiClient.get(`/model-center/download/${taskId}`);
  return response.data;
};

// 获取推荐模型列表
export const getModelSuggestions = async () => {
  const response = await apiClient.get('/model-center/suggestions');
  return response.data;
};

// 获取本地模型列表
export const getLocalModels = async () => {
  const response = await apiClient.get('/model-center/local');
  return response.data;
};

// 删除本地模型
export const deleteLocalModel = async (modelId: string) => {
  const response = await apiClient.delete(`/model-center/local/${modelId}`);
  return response.data;
};

// 获取模型下载源配置
export const getModelSource = async () => {
  const response = await apiClient.get('/model-center/source');
  return response.data;
};

// 切换模型下载源
export const setModelSource = async (source: string) => {
  const response = await apiClient.post('/model-center/source', null, { params: { source } });
  return response.data;
};

// 检查网络状态
export const checkNetworkStatus = async () => {
  const response = await apiClient.get('/model-center/network/status');
  return response.data;
};

// 数据集管理
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
    headers: { 'Content-Type': 'multipart/form-data' }
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

// 训练管理
export const startTraining = async (config: any) => {
  const response = await apiClient.post('/training/start', config);
  return response.data;
};

// P2-2: SWIFT 框架训练
export const startSwiftTraining = async (config: any) => {
  const response = await apiClient.post('/training/start-swift', config);
  return response.data;
};

export const stopTraining = async () => {
  const response = await apiClient.post('/training/stop');
  return response.data;
};

export const getTrainingProgress = async () => {
  const response = await apiClient.get('/training/progress');
  return response.data;
};

export const subscribeTrainingProgress = (
  onProgress: (progress: any) => void,
  onError?: (error: Error) => void,
  retryConfig?: Partial<RetryConfig>
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
        console.warn(`SSE 连接断开，${backoffDelay}ms 后重试 (第 ${retryCount + 1}/${config.maxRetries} 次)`);
        retryCount++;
        retryTimer = setTimeout(connect, backoffDelay);
      } else {
        if (onError) {
          onError(new Error('SSE 连接错误，已达到最大重试次数'));
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

export const getTrainingHistory = async () => {
  const response = await apiClient.get('/training/history');
  return response.data;
};

export const resumeTraining = async (trainingId: string, checkpoint: string) => {
  const response = await apiClient.post(`/training/resume/${trainingId}/${checkpoint}`);
  return response.data;
};

// 推理服务
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
  retryConfig?: Partial<RetryConfig>
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
      
      while (!done) {
        if (Date.now() - streamStartTime > STREAM_READ_TIMEOUT) {
          throw new Error('流式读取超时');
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
              onChunk(data.content);
            }

            if (data.done) {
              if (data.stats && onStats) {
                onStats(data.stats);
              }
              console.log(`流式推理完成 - 共 ${chunkCount} 个 chunks`);
            }
          } catch (e) {
            if (e instanceof Error && e.message !== 'Stream error') {
              console.error('Parse SSE error:', e, 'Raw:', parsed.data);
            } else {
              throw e;
            }
          }
        }
      }
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
        console.log('流式推理已被取消');
        throw error;
      }

      if (!isRetryableError(error)) {
        throw error;
      }

      if (attempt < retryConf.maxRetries - 1) {
        const backoffDelay = calculateBackoff(attempt, retryConf.baseDelay, retryConf.maxDelay);
        console.warn(`流式推理失败，${backoffDelay}ms 后重试 (第 ${attempt + 1}/${retryConf.maxRetries} 次):`, error.message);
        await delay(backoffDelay);
      }
    }
  }

  throw lastError;
};

export const chatInference = async (
  modelId: string,
  messages: Array<{ role: string; content: string }>,
  options?: { maxTokens?: number; temperature?: number }
) => {
  const response = await apiClient.post('/inference/chat', {
    model_id: modelId,
    messages,
    ...options,
  });
  return response.data;
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

export const getInferenceModels = async () => {
  const response = await apiClient.get('/inference/models');
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

export const clearPerformanceHistory = async () => {
  const response = await apiClient.post('/inference/performance/clear');
  return response.data;
};

// 对话历史管理
export const getChatHistory = async (retryConfig?: Partial<RetryConfig>) => {
  return fetchWithRetry(async () => {
    const response = await fetch(`${API_BASE_URL}/chat`);
    if (!response.ok) throw new Error('Failed to fetch chat history');
    const data = await response.json();
    return data.sessions || [];
  }, retryConfig);
};

export const createChatSession = async (title: string, modelId: string, retryConfig?: Partial<RetryConfig>) => {
  return fetchWithRetry(async () => {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, metadata: { model_id: modelId } })
    });
    if (!response.ok) throw new Error('Failed to create session');
    return response.json();
  }, retryConfig);
};

export const getChatSession = async (sessionId: string, retryConfig?: Partial<RetryConfig>) => {
  return fetchWithRetry(async () => {
    const response = await fetch(`${API_BASE_URL}/chat/${sessionId}`);
    if (!response.ok) throw new Error('Failed to fetch session');
    return response.json();
  }, retryConfig);
};

export const deleteChatSession = async (sessionId: string, retryConfig?: Partial<RetryConfig>) => {
  return fetchWithRetry(async () => {
    const response = await fetch(`${API_BASE_URL}/chat/${sessionId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error('Failed to delete session');
    return response.json();
  }, retryConfig);
};

export const addChatMessages = async (
  sessionId: string,
  messages: Array<{ id: string; role: string; content: string; timestamp: string }>,
  retryConfig?: Partial<RetryConfig>
) => {
  return fetchWithRetry(async () => {
    const response = await fetch(`${API_BASE_URL}/chat/${sessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages })
    });
    if (!response.ok) throw new Error('Failed to add messages');
    return response.json();
  }, retryConfig);
};

export const mergeLora = async (modelId: string, outputName: string) => {
  const response = await apiClient.post(`/models/${modelId}/merge`, { output_name: outputName });
  return response.data;
};

// ==================== Agent 操作 API ====================

/**
 * 检测消息中的 Agent 意图
 */
export const detectAgentIntent = async (message: string) => {
  const response = await apiClient.post('/agent/detect-intent', { message });
  return response.data;
};

/**
 * 执行 Agent 操作
 */
export const executeAgentAction = async (
  action: string,
  params: Record<string, any>,
  confirm: boolean = false
) => {
  const response = await apiClient.post('/agent/execute', { action, params, confirm });
  return response.data;
};

/**
 * 从聊天消息自动识别并执行操作
 */
export const chatExecuteAgent = async (
  message: string, 
  autoConfirm: boolean = false,
  context?: { content?: string; content_type?: string; generated_filename?: string }
) => {
  const response = await apiClient.post('/agent/chat-execute', { 
    message, 
    auto_confirm: autoConfirm,
    context 
  });
  return response.data;
};

/**
 * 获取 Agent 支持的操作能力
 */
export const getAgentCapabilities = async () => {
  const response = await apiClient.get('/agent/capabilities');
  return response.data;
};

/**
 * 获取审计统计信息
 */
export const getAgentAuditStats = async () => {
  const response = await apiClient.get('/agent/audit/stats');
  return response.data;
};

/**
 * 获取最近的审计日志
 */
export const getAgentAuditRecent = async (limit: number = 50) => {
  const response = await apiClient.get('/agent/audit/recent', { params: { limit } });
  return response.data;
};

/**
 * 增强版意图检测（支持多意图、置信度评分）
 */
export const detectIntentEnhanced = async (
  message: string,
  context?: Record<string, any>
) => {
  const response = await apiClient.post('/agent/detect-intent-enhanced', { message, context });
  return response.data;
};

/**
 * 多意图并行检测
 */
export const detectMultiIntent = async (
  message: string,
  context?: Record<string, any>,
  maxIntents: number = 5
) => {
  const response = await apiClient.post('/agent/detect-multi-intent', {
    message,
    context,
    max_intents: maxIntents,
  });
  return response.data;
};

/**
 * 处理澄清对话响应
 */
export const handleClarificationResponse = async (
  dialogId: string,
  response: string
) => {
  const res = await apiClient.post('/agent/clarification/respond', {
    dialog_id: dialogId,
    response,
  });
  return res.data;
};

/**
 * 获取澄清对话详情
 */
export const getClarificationDialog = async (dialogId: string) => {
  const response = await apiClient.get(`/agent/clarification/${dialogId}`);
  return response.data;
};

/**
 * 从自然语言中提取结构化参数
 */
export const extractParams = async (
  message: string,
  paramTypes?: string[]
) => {
  const response = await apiClient.post('/agent/extract-params', {
    message,
    param_types: paramTypes,
  });
  return response.data;
};

/**
 * 获取支持的意图类型列表
 */
export const getIntentTypes = async () => {
  const response = await apiClient.get('/agent/intent-types');
  return response.data;
};

/**
 * 评估意图置信度详情
 */
export const evaluateIntentConfidence = async (
  message: string,
  context?: Record<string, any>
) => {
  const response = await apiClient.post('/agent/intent-confidence', { message, context });
  return response.data;
};

// 健康检查
export const checkBackendHealth = async () => {
  try {
    const response = await apiClient.get('/health');
    return response.status === 200;
  } catch {
    return false;
  }
};

// ==================== CUA API ====================

export const cua = {
  getScreenInfo: () => apiClient.get('/cua/screen/info'),
  takeScreenshot: (params: { monitor?: number; region?: { x: number; y: number; width: number; height: number }; format?: string; quality?: number }) =>
    apiClient.post('/cua/screenshot', params),
  getMousePosition: () => apiClient.get('/cua/mouse/position'),
  mouseClick: (params: { x: number; y: number; button?: string; clicks?: number }) =>
    apiClient.post('/cua/mouse/click', params),
  mouseMove: (params: { x: number; y: number; duration?: number }) =>
    apiClient.post('/cua/mouse/move', params),
  mouseDrag: (params: { start_x: number; start_y: number; end_x: number; end_y: number; duration?: number; button?: string }) =>
    apiClient.post('/cua/mouse/drag', params),
  mouseScroll: (params: { clicks: number; x?: number; y?: number }) =>
    apiClient.post('/cua/mouse/scroll', params),
  keyboardType: (params: { text: string; interval?: number }) =>
    apiClient.post('/cua/keyboard/type', params),
  keyboardPress: (params: { key: string }) =>
    apiClient.post('/cua/keyboard/press', params),
  keyboardHotkey: (params: { keys: string[] }) =>
    apiClient.post('/cua/keyboard/hotkey', params),
  listWindows: () => apiClient.get('/cua/window/list'),
  getActiveWindow: () => apiClient.get('/cua/window/active'),
  activateWindow: (windowId: string) => apiClient.post('/cua/window/activate', { window_id: windowId }),
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
  setPermissionLevel: (level: string) => apiClient.post('/cua/safety/permission', null, { params: { level } }),
  getAuditLogs: (limit?: number) => apiClient.get('/cua/safety/logs', { params: { limit } }),
};

// ==================== MCP API ====================

export const mcp = {
  listTools: () => apiClient.get('/mcp/tools'),
  callTool: (params: { tool_name: string; arguments: object }) =>
    apiClient.post('/mcp/call', params),
  listServers: () => apiClient.get('/mcp/servers'),
  addServer: (params: { name: string; transport: string; command?: string; args?: string[]; url?: string }) =>
    apiClient.post('/mcp/servers', params),
  removeServer: (name: string) => apiClient.delete(`/mcp/servers/${name}`),
  getServerStatus: (name: string) => apiClient.get(`/mcp/servers/${name}/status`),
  reconnectServer: (name: string) => apiClient.post(`/mcp/servers/${name}/reconnect`),
  getServerTools: (name: string) => apiClient.get(`/mcp/servers/${name}/tools`),
  getOverallStatus: () => apiClient.get('/mcp/status'),
};

export default apiClient;
