export interface DeviceInfo {
  platform: 'cuda' | 'mac' | 'unknown' | string
  device_name: string
  vram_total: number
  vram_used: number
  vram_free: number
  memory_total: number
  memory_used: number
  memory_free: number
  cuda_available: boolean
  mps_available: boolean
  cpu_count?: number
  cpu_percent?: number
}

export interface ModelInfo {
  id: string
  name: string
  path: string
  size: number
  type: 'base' | 'lora' | 'merged'
  quantized?: number
  createdAt: string
}

export interface DatasetInfo {
  id: string
  name: string
  path: string
  size: number
  format: 'json' | 'jsonl'
  samples: number
  createdAt: string
}

export interface TrainingConfig {
  modelId: string
  datasetId: string
  method: 'lora' | 'qlora' | 'full' | 'dora'
  rank: number
  alpha: number
  learningRate: number
  epochs: number
  batchSize: number
  gradientAccumulation: number
  maxSeqLength: number
  warmupSteps: number
  saveSteps: number
  loggingSteps: number
  // P2-3: 高精度选项
  useDora?: boolean
  lrScheduler?: 'cosine' | 'linear' | 'constant'
  warmupRatio?: number
  weightDecay?: number
  labelSmoothing?: number
  gradientCheckpointing?: boolean
  bf16?: boolean
  evalSteps?: number
  loadBestModel?: boolean
  targetModules?: 'all' | 'mlp' | 'attn'
  loraDropout?: number
  maxGradNorm?: number
  precisionPreset?: 'max' | 'balanced' | 'fast'
  // P2-4: 低显存优化选项
  memoryPreset?: 'auto' | '6gb' | '8gb' | '12gb'
  useFlashAttn?: boolean
  deepspeedStage?: number
  offloadOptimizer?: boolean
  quantization?: 0 | 4 | 8
}

export interface TrainingProgress {
  epoch: number
  step: number
  totalSteps: number
  loss: number
  lr: number
  vramUsed: number
  elapsedTime: number
  eta: number
  status?: 'idle' | 'loading' | 'training' | 'running' | 'completed' | 'failed' | 'stopped'
  message?: string
}

export interface TrainingRecord {
  id: string
  modelName: string
  datasetName: string
  method: string
  status: 'running' | 'completed' | 'failed' | 'stopped'
  startTime: string
  endTime?: string
  config: TrainingConfig
  outputPath: string
  checkpointPath?: string
}

export interface Checkpoint {
  name: string
  path: string
  step: number
  created: string
}

export interface InferenceRequest {
  modelId: string
  prompt: string
  maxTokens: number
  temperature: number
  topP?: number
  backend?: string
}

export interface InferenceResponse {
  text: string
  tokens: number
  time: number
  knowledge_sources?: KnowledgeSource[]
  retrieval_info?: RetrievalInfo
}

export interface KnowledgeSource {
  id: string
  source: string
  score: number
  content_preview: string
}

export interface RetrievalInfo {
  query: string
  method: string
  total_results: number
  retrieval_time: number
}

export interface BackendInfo {
  id: string
  name: string
  available: boolean
  description: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp?: string
  isLoading?: boolean
  knowledge_sources?: KnowledgeSource[]
  retrieval_info?: RetrievalInfo
}

export interface ChatSession {
  id: string
  title: string
  model_id?: string
  created_at?: string
  updated_at?: string
  message_count?: number
  messages?: ChatMessage[]
}

interface ElectronAPI {
  selectFolder: (defaultPath?: string) => Promise<string | null>
  selectFile: (filters?: { name: string; extensions: string[] }[]) => Promise<string | null>
  readFile: (filePath: string) => Promise<{ data: string; name: string } | null>
  getBackendUrl: () => Promise<string>
  restartBackend: () => Promise<boolean>
  openFolder: (folderPath: string) => Promise<void>
  getAppPath: () => Promise<string>
  onTrainingProgress: (callback: (data: unknown) => void) => void
  onTrainingComplete: (callback: (data: unknown) => void) => void
  onTrainingError: (callback: (data: unknown) => void) => void
  removeTrainingListeners: () => void
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

// ==================== CUA Types ====================

export interface ScreenInfo {
  width: number;
  height: number;
  monitorCount: number;
}

export interface MousePosition {
  x: number;
  y: number;
}

export interface WindowInfo {
  id: string;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  is_active: boolean;
}

export interface SafetyStatus {
  enabled: boolean;
  permissionLevel: 'read_only' | 'interactive' | 'full_control';
  failsafeEnabled: boolean;
  auditEnabled: boolean;
}

export interface RecordedAction {
  action_type: string;
  timestamp: number;
  data: Record<string, unknown>;
}

// ==================== MCP Types ====================

export interface MCPTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface MCPServerInfo {
  name: string;
  transport: 'stdio' | 'sse';
  command?: string;
  args?: string[];
  url?: string;
  status: 'connected' | 'disconnected';
}

export interface MCPToolResult {
  call_id: string;
  content: unknown;
  is_error: boolean;
}

export {}
