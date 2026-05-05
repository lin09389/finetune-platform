export interface DeviceInfo {
  platform: 'cuda' | 'mac' | 'unknown' | string;
  device_name: string;
  vram_total: number;
  vram_used: number;
  vram_free: number;
  memory_total: number;
  memory_used: number;
  memory_free: number;
  cuda_available: boolean;
  mps_available: boolean;
  cpu_count?: number;
  cpu_percent?: number;
}

export interface ModelInfo {
  id: string;
  name: string;
  path: string;
  size: number;
  type: 'base' | 'lora' | 'merged';
  quantized?: number;
  createdAt: string;
}

export interface DatasetInfo {
  id: string;
  name: string;
  path: string;
  size: number;
  format: 'json' | 'jsonl';
  samples: number;
  createdAt: string;
}

export type AppTaskGoal = 'qa_assistant' | 'structured_extraction';

export interface DatasetAnalysisResult {
  detected_format: string;
  field_candidates: Record<string, string[]>;
  sample_count: number;
  valid_count: number;
  errors: Array<{ line: number; message: string; severity: string }>;
  warnings: Array<{ line: number; message: string; severity: string }>;
  length_stats: {
    min_chars: number;
    max_chars: number;
    avg_chars: number;
    overlong_ratio: number;
  };
  recommended_target_format: string;
  health: {
    json_valid_ratio: number;
    field_completeness: number;
    overlong_sample_ratio: number;
    duplicate_sample_ratio: number;
    trainable_sample_count: number;
  };
}

export interface TrainingConfig {
  modelId: string;
  model_id?: string;
  datasetId: string;
  dataset_id?: string;
  taskGoal?: AppTaskGoal;
  task_goal?: AppTaskGoal;
  testDatasetId?: string;
  test_dataset_id?: string;
  validationDatasetId?: string;
  validation_dataset_id?: string;
  method: 'lora' | 'qlora' | 'full' | 'dora';
  rank: number;
  alpha: number;
  learningRate: number;
  epochs: number;
  batchSize: number;
  gradientAccumulation: number;
  maxSeqLength: number;
  warmupSteps: number;
  saveSteps: number;
  loggingSteps: number;
  // P2-3: 高精度选项
  useDora?: boolean;
  lrScheduler?: 'cosine' | 'linear' | 'constant';
  warmupRatio?: number;
  weightDecay?: number;
  labelSmoothing?: number;
  gradientCheckpointing?: boolean;
  bf16?: boolean;
  evalSteps?: number;
  loadBestModel?: boolean;
  targetModules?: 'all' | 'mlp' | 'attn';
  loraDropout?: number;
  maxGradNorm?: number;
  precisionPreset?: 'max' | 'balanced' | 'fast';
  // P2-4: 低显存优化选项
  memoryPreset?: 'auto' | '6gb' | '8gb' | '12gb';
  useFlashAttn?: boolean;
  deepspeedStage?: number;
  offloadOptimizer?: boolean;
  quantization?: 0 | 4 | 8;
}

export interface EvaluationRun {
  run_id: string;
  scenario: AppTaskGoal;
  status: string;
  created_at: string;
  base_model: string;
  finetuned_model?: string;
  adapter_path?: string;
  adapter_merge?: {
    merged_model_path?: string;
    adapter_path?: string;
    backend?: string;
  } | null;
  test_dataset_id?: string;
  base_outputs: unknown[];
  finetuned_outputs: unknown[];
  cases: Array<Record<string, unknown>>;
  metrics: Record<string, number>;
  failed_cases: Array<Record<string, unknown>>;
  human_scores: Array<Record<string, unknown>>;
  backend?: string;
  run_inference?: boolean;
  warnings?: string[];
  inference_options?: {
    max_tokens?: number;
    temperature?: number;
    max_cases?: number;
    auto_merge_adapter?: boolean;
  };
}

export interface DeploymentPackage {
  package_id: string;
  training_task_id: string;
  created_at: string;
  base_model: string;
  adapter_path: string;
  merged_model_path?: string;
  ollama_modelfile?: string;
  openai_compatible_examples: Record<string, string>;
  env_template: Record<string, string>;
}

export interface TrainingProgress {
  epoch: number;
  step: number;
  totalSteps: number;
  loss: number;
  lr: number;
  vramUsed: number;
  elapsedTime: number;
  eta: number;
  status?:
    | 'idle'
    | 'loading'
    | 'training'
    | 'running'
    | 'stopping'
    | 'completed'
    | 'failed'
    | 'stopped';
  message?: string;
  queuePosition?: number;
  estimatedWaitSeconds?: number;
  errorCode?: string;
  errorCategory?: string;
  actionableSuggestions?: string[];
}

export interface TrainingRecord {
  id: string;
  modelName: string;
  datasetName: string;
  baseModelId: string;
  datasetId: string;
  taskGoal?: AppTaskGoal;
  adapterPath?: string;
  method: string;
  status: 'running' | 'completed' | 'failed' | 'stopped';
  startTime: string;
  endTime?: string;
  config: TrainingConfig;
  outputPath: string;
  checkpointPath?: string;
  finalLoss?: number;
  finalLr?: number;
  elapsedTime?: number;
  totalSteps?: number;
}

export interface Checkpoint {
  name: string;
  path: string;
  step: number;
  created: string;
}

export interface InferenceRequest {
  modelId: string;
  prompt: string;
  maxTokens: number;
  temperature: number;
  topP?: number;
  backend?: string;
}

export interface InferenceResponse {
  text: string;
  tokens: number;
  time: number;
  knowledge_sources?: KnowledgeSource[];
  retrieval_info?: RetrievalInfo;
}

export interface KnowledgeSource {
  id: string;
  source: string;
  score: number;
  content_preview: string;
}

export interface RetrievalInfo {
  query: string;
  method: string;
  total_results: number;
  retrieval_time: number;
}

export type PlaygroundAttachmentType = 'text' | 'image';

export interface PlaygroundAttachment {
  id: string;
  name: string;
  type: PlaygroundAttachmentType;
  mimeType: string;
  size: number;
  content?: string;
  previewUrl?: string;
}

export interface PlaygroundRunMetrics {
  model?: string;
  backend?: string;
  duration_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  used_knowledge?: boolean;
  used_memory?: boolean;
}

export type PlaygroundCandidateStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'completed'
  | 'error'
  | 'stopped';

export interface PlaygroundCandidate {
  id: string;
  index: number;
  content: string;
  status: PlaygroundCandidateStatus;
  error?: string;
  raw_response?: unknown;
  knowledge_sources?: KnowledgeSource[];
  retrieval_info?: RetrievalInfo;
  memory_context?: {
    retrieved: boolean;
    sources_count: number;
    context_preview: string;
  };
  unified_context?: {
    total_sources: number;
    memory_count: number;
    knowledge_count: number;
    project_count?: number;
    retrieval_time: number;
  };
  run_metrics?: PlaygroundRunMetrics;
}

export interface PlaygroundExperimentConfig {
  prompt: string;
  systemPrompt: string;
  responseFormat: 'text' | 'json';
  modelId: string;
  backend: 'ollama' | 'huggingface' | 'cloud' | 'llama-cpp';
  temperature: number;
  topP: number;
  maxTokens: number;
  useKnowledge: boolean;
  knowledgeCollection?: string;
  useMemory: boolean;
  autoRetrieve: boolean;
  candidateCount: number;
  attachments: PlaygroundAttachment[];
}

export interface PlaygroundSnapshot {
  id: string;
  createdAt: string;
  lastViewedAt?: string;
  isFavorite?: boolean;
  title: string;
  response: string;
  selectedCandidateId: string;
  candidates: PlaygroundCandidate[];
  raw_response?: unknown;
  knowledge_sources?: KnowledgeSource[];
  retrieval_info?: RetrievalInfo;
  memory_context?: {
    retrieved: boolean;
    sources_count: number;
    context_preview: string;
  };
  unified_context?: {
    total_sources: number;
    memory_count: number;
    knowledge_count: number;
    project_count?: number;
    retrieval_time: number;
  };
  experiment_config: PlaygroundExperimentConfig;
  run_metrics?: PlaygroundRunMetrics;
}

export interface PlaygroundPreset {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  config: PlaygroundExperimentConfig;
}

export interface BackendInfo {
  id: string;
  name: string;
  available: boolean;
  description: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  isLoading?: boolean;
  knowledge_sources?: KnowledgeSource[];
  retrieval_info?: RetrievalInfo;
  memory_context?: PlaygroundSnapshot['memory_context'];
  unified_context?: PlaygroundSnapshot['unified_context'];
  raw_response?: unknown;
  attachments?: PlaygroundAttachment[];
  experiment_config?: Partial<PlaygroundExperimentConfig>;
  run_metrics?: PlaygroundRunMetrics;
  isEdited?: boolean;
  agent_metadata?: ChatAgentMetadata;
}

export type ChatAgentMessageKind =
  | 'agent_part'
  | 'agent_run_card'
  | 'agent_step_update'
  | 'agent_approval_request'
  | 'agent_action_proposal'
  | 'agent_action_execution'
  | 'agent_final_summary'
  | 'agent_error';

export interface ChatAgentMetadata {
  agent_run_id: string;
  agent_session_id?: string;
  agent_part_id?: string;
  workflow_id?: string;
  kind: ChatAgentMessageKind;
  status: string;
  step_id?: string;
  action_id?: string;
  action_type?: 'patch' | 'command' | string;
  can_approve?: boolean;
  can_execute?: boolean;
  details_url?: string;
  active_agent_id?: string;
  subagent_runs?: Array<Record<string, unknown>>;
  workflow?: unknown;
  observability?: unknown;
  tool_calls?: unknown[];
  permission_pending?: boolean;
  latest_blocked_tool?: string;
  execution_state?: string;
  execution_state_message?: string;
  final_summary?: string;
  recoverable?: boolean;
  model_protocol_status?: 'ok' | 'repaired' | 'fallback_summary' | 'needs_manual_review' | string;
  last_model_output_preview?: string;
  parse_repair_count?: number;
  fallback_summary_used?: boolean;
  acceptance_report?: ChatAgentAcceptanceReport;
  acceptance_report_source?: 'model' | 'fallback' | string;
  acceptance_report_raw?: string;
  blocked_state?: Record<string, unknown> | null;
  autonomy_mode?: 'safe_auto' | 'confirm_all' | 'read_only';
  auto_execution_policy?: Record<string, unknown>;
  repair_attempts?: number;
  max_repair_attempts?: number;
  action?: unknown;
  event?: unknown;
  latest_event?: unknown;
  latest_tool_call?: unknown;
  latest_action?: unknown;
  agent_parts?: unknown[];
  agent_part?: unknown;
  agent_session_state?: unknown;
  agent_session_diagnostics?: {
    status?: string;
    current_phase?: string;
    stop_reason?: string;
    next_action?: string;
    refresh_safe?: boolean;
    latest_event?: unknown;
    latest_tool_call?: unknown;
    latest_tool_result?: unknown;
    latest_action?: unknown;
    latest_command?: unknown;
    latest_summary?: unknown;
    latest_error?: unknown;
    recent_events?: unknown[];
  };
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

export interface ChatSession {
  id: string;
  title: string;
  model_id?: string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
  messages?: ChatMessage[];
}

interface ElectronAPI {
  selectFolder: (defaultPath?: string) => Promise<string | null>;
  selectFile: (filters?: { name: string; extensions: string[] }[]) => Promise<string | null>;
  readFile: (filePath: string) => Promise<{ data: string; name: string } | null>;
  getBackendUrl: () => Promise<string>;
  restartBackend: () => Promise<boolean>;
  openFolder: (folderPath: string) => Promise<void>;
  getAppPath: () => Promise<string>;
  onTrainingProgress: (callback: (data: unknown) => void) => void;
  onTrainingComplete: (callback: (data: unknown) => void) => void;
  onTrainingError: (callback: (data: unknown) => void) => void;
  removeTrainingListeners: () => void;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
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

export {};
