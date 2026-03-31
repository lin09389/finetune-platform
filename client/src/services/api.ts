/**
 * API 鏈嶅姟閰嶇疆
 * 鏀寔杩炴帴澶嶇敤銆佽姹傚彇娑堛€侀敊璇嚜鍔ㄩ噸璇? */
import axios, { AxiosInstance } from 'axios';

// 鑾峰彇 API 鍩虹 URL
const getApiBaseUrl = () => {
  if (typeof window !== 'undefined' && (window as any).electronAPI) {
    return (window as any).electronAPI.getBackendUrlSync?.() || 'http://127.0.0.1:8000';
  }
  return ((import.meta as any).env?.VITE_API_URL || 'http://127.0.0.1:8000') as string;
};

// Export base URL for other modules.
export const API_BASE_URL = getApiBaseUrl();

// ==================== 杩炴帴姹犵鐞?====================

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

// ==================== 閿欒閲嶈瘯鏈哄埗 ====================

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
        console.warn(`璇锋眰澶辫触锛?{backoffDelay}ms 鍚庨噸璇?(绗?${attempt + 1}/${retryConfig.maxRetries} 娆?:`, error.message);
        await delay(backoffDelay);
      }
    }
  }

  throw lastError;
}

// ==================== Axios 瀹炰緥閰嶇疆 ====================

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

// ==================== 璇锋眰鍙栨秷绠＄悊 ====================

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

// 璁惧绠＄悊
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

// 妯″瀷绠＄悊
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

// 瀵煎叆 ModelScope 妯″瀷
export const importModelFromModelScope = async (modelName: string, modelscopePath?: string) => {
  const response = await apiClient.post('/model-center/import-modelscope', {
    model_name: modelName,
    modelscope_path: modelscopePath
  });
  return response.data;
};

// Search models (ModelScope / HuggingFace)
export const searchModels = async (query: string, limit: number = 20, source: string = 'modelscope') => {
  const response = await apiClient.post('/model-center/search', {
    query,
    limit,
    source
  });
  return response.data;
};

// 浠?ModelScope 涓嬭浇妯″瀷
export const downloadModelFromModelScope = async (repoId: string, revision: string = 'master') => {
  const response = await apiClient.post('/model-center/download', {
    repo_id: repoId,
    revision,
    source: 'modelscope'
  });
  return response.data;
};

// 浠?HuggingFace 涓嬭浇妯″瀷
export const downloadModelFromHuggingFace = async (repoId: string, revision: string = 'main') => {
  const response = await apiClient.post('/model-center/download', {
    repo_id: repoId,
    revision,
    source: 'huggingface'
  });
  return response.data;
};

// 鑾峰彇妯″瀷涓嬭浇杩涘害
export const getDownloadProgress = async (taskId: string) => {
  const response = await apiClient.get(`/model-center/download/${taskId}`);
  return response.data;
};

// 鑾峰彇鎺ㄨ崘妯″瀷鍒楄〃
export const getModelSuggestions = async () => {
  const response = await apiClient.get('/model-center/suggestions');
  return response.data;
};

// 鑾峰彇鏈湴妯″瀷鍒楄〃
export const getLocalModels = async () => {
  const response = await apiClient.get('/model-center/local');
  return response.data;
};

// 鍒犻櫎鏈湴妯″瀷
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

// 璁粌绠＄悊
export const startTraining = async (config: any) => {
  const response = await apiClient.post('/training/start', config);
  return response.data;
};

// P2-2: SWIFT 妗嗘灦璁粌
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
        console.warn(`SSE 杩炴帴鏂紑锛?{backoffDelay}ms 鍚庨噸璇?(绗?${retryCount + 1}/${config.maxRetries} 娆?`);
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

export const getTrainingHistory = async () => {
  const response = await apiClient.get('/training/history');
  return response.data;
};

export const resumeTraining = async (trainingId: string, checkpoint: string) => {
  const response = await apiClient.post(`/training/resume/${trainingId}/${checkpoint}`);
  return response.data;
};

// 鎺ㄧ悊鏈嶅姟
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
          throw new Error('娴佸紡璇诲彇瓒呮椂');
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
              console.log(`娴佸紡鎺ㄧ悊瀹屾垚 - 鍏?${chunkCount} 涓?chunks`);
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
        console.log('娴佸紡鎺ㄧ悊宸茶鍙栨秷');
        throw error;
      }

      if (!isRetryableError(error)) {
        throw error;
      }

      if (attempt < retryConf.maxRetries - 1) {
        const backoffDelay = calculateBackoff(attempt, retryConf.baseDelay, retryConf.maxDelay);
        console.warn(`娴佸紡鎺ㄧ悊澶辫触锛?{backoffDelay}ms 鍚庨噸璇?(绗?${attempt + 1}/${retryConf.maxRetries} 娆?:`, error.message);
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

// 瀵硅瘽鍘嗗彶绠＄悊
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

// ==================== Agent APIs (Direct-Cut Contract) ====================

/**
 * Detect intent from plain user message.
 */
export const detectAgentIntent = async (message: string) => {
  const response = await apiClient.post('/agent/detect-intent', { message });
  return response.data;
};

/**
 * Execute a concrete agent action directly.
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
 * Detect and execute from chat message in one request.
 */
export const chatExecuteAgent = async (
  message: string, 
  autoConfirm: boolean = false,
  context?: { content?: string; content_type?: string; generated_filename?: string },
  sessionId?: string
) => {
  const response = await apiClient.post('/agent/chat-execute', { 
    message, 
    auto_confirm: autoConfirm,
    context,
    session_id: sessionId
  });
  return response.data;
};

/**
 * Get backend-declared agent capabilities.
 */
export const getAgentCapabilities = async () => {
  const response = await apiClient.get('/agent/capabilities');
  return response.data;
};

/**
 * @deprecated `/agent/audit/*` removed in direct-cut mode.
 * Compatibility wrapper maps to `/agent-executor/stats`.
 */
export const getAgentAuditStats = async () => {
  const response = await apiClient.get('/agent-executor/stats');
  return {
    source: 'agent-executor',
    ...response.data,
  };
};

/**
 * @deprecated `/agent/audit/*` removed in direct-cut mode.
 * Compatibility wrapper maps to `/agent-executor/audit-log`.
 */
export const getAgentAuditRecent = async (limit: number = 50) => {
  const response = await apiClient.get('/agent-executor/audit-log', { params: { limit } });
  return {
    source: 'agent-executor',
    ...response.data,
  };
};

/**
 * Compatibility wrapper for richer intent detection payload.
 */
export const detectIntentEnhanced = async (
  message: string,
  context?: Record<string, any>
) => {
  const response = await apiClient.post('/agent/detect-intent', { message, context });
  return response.data;
};

/**
 * Multi-intent detection entrypoint.
 */
export const detectMultiIntent = async (
  message: string,
  context?: Record<string, any>,
  _maxIntents: number = 5
) => {
  const response = await apiClient.post('/agent/detect-intent-multi', {
    message,
    context,
  });
  return response.data;
};

/**
 * Local clarification helper kept for UI compatibility.
 */
export const handleClarificationResponse = async (
  _dialogId: string,
  response: string
) => {
  return {
    success: true,
    selected_option: {
      value: response,
    },
  };
};

export const getClarificationDialog = async (_dialogId: string) => {
  return {
    question: '',
    options: [],
    context: {},
  };
};

export const extractParams = async (
  message: string,
  _paramTypes?: string[]
) => {
  const response = await apiClient.post('/agent/detect-intent', { message });
  const data = response.data || {};
  return {
    success: true,
    params: data.params || {},
    confidence: data.confidence ?? 0,
    intent_type: data.intent_type ?? 'unknown',
  };
};

export const getIntentTypes = async () => {
  return {
    intent_types: [
      'content_generation',
      'save_content',
      'composite_content_save',
      'conversation',
      'unknown',
    ],
  };
};

export const evaluateIntentConfidence = async (
  message: string,
  context?: Record<string, any>
) => {
  const response = await apiClient.post('/agent/detect-intent', { message, context });
  const data = response.data || {};
  return {
    confidence: data.confidence ?? 0,
    intent_type: data.intent_type ?? 'unknown',
    detected: Boolean(data.detected),
  };
};

// Health check
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

// ==================== 鎺ㄧ悊寮曟搸 API (閲嶆瀯鐗? ====================

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

export const listInferenceEngines = async (): Promise<{ engines: InferenceEngine[]; default_engine: string }> => {
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
  onComplete?: () => void
) => {
  const response = await fetch(`${API_BASE_URL}/inference-engine/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
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

// ==================== Agent 鎵ц鍣?API (閲嶆瀯鐗? ====================

export interface OperationResult {
  success: boolean;
  status: string;
  message: string;
  data?: Record<string, any>;
  error?: string;
  error_code?: string;
  operation_id: string;
  duration_ms: number;
}

export interface ExecuteRequest {
  action: string;
  params: Record<string, any>;
  workspace?: string;
}

export const listAgentActions = async (): Promise<{ actions: string[]; count: number; executor: string }> => {
  const response = await apiClient.get('/agent-executor/actions');
  return response.data;
};

export const executeAgentActionNew = async (request: ExecuteRequest): Promise<OperationResult> => {
  const response = await apiClient.post('/agent-executor/execute', request);
  return response.data;
};

export const executeAgentBatch = async (
  operations: Array<{ action: string; params: Record<string, any> }>,
  workspace?: string
): Promise<{ results: OperationResult[]; total: number }> => {
  const response = await apiClient.post('/agent-executor/execute/batch', { operations, workspace });
  return response.data;
};

export const listAgentHandlers = async () => {
  const response = await apiClient.get('/agent-executor/handlers');
  return response.data;
};

export const getAgentExecutorStats = async () => {
  const response = await apiClient.get('/agent-executor/stats');
  return response.data;
};

export const getAgentAuditLog = async (limit: number = 100) => {
  const response = await apiClient.get(`/agent-executor/audit-log?limit=${limit}`);
  return response.data;
};

export default apiClient;

