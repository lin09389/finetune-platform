/**
 * 推理相关类型定义
 */

export interface InferenceRequest {
  model_id: string;
  prompt: string;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  top_k?: number;
  repetition_penalty?: number;
  backend?: 'huggingface' | 'ollama';
  lora_adapter?: string;
}

export interface InferenceResponse {
  text: string;
  tokens: number;
  time: number;
  model_id: string;
  backend: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface MemoryOptions {
  enabled: boolean;
  auto_extract?: boolean;
  auto_retrieve?: boolean;
  top_k?: number;
  include_types?: string[];
}

export interface KnowledgeOptions {
  use_knowledge: boolean;
  collection_id?: string;
  auto_retrieve?: boolean;
  top_k?: number;
  include_sources?: boolean;
}

export interface SessionOptions {
  session_id?: string;
  user_id?: string;
}

export interface ChatRequest {
  model_id: string;
  messages: ChatMessage[];
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  backend?: 'huggingface' | 'ollama';
  memory?: MemoryOptions;
  knowledge?: KnowledgeOptions;
  session?: SessionOptions;
}

export interface MemoryContextInfo {
  retrieved: boolean;
  sources_count: number;
  context_preview: string;
}

export interface UnifiedContextInfo {
  total_sources: number;
  memory_count: number;
  knowledge_count: number;
  project_count: number;
  retrieval_time: number;
  budget?: Record<string, unknown>;
  warnings?: string[];
  trace?: Record<string, unknown>;
}

export interface BackendInfo {
  id: string;
  name: string;
  available: boolean;
  description: string;
}

export interface BackendsResponse {
  current: string;
  backends: BackendInfo[];
}

export interface OllamaStatus {
  running: boolean;
  base_url: string;
  models: Array<{ name: string; size: number }>;
}

export interface MergeRequest {
  base_model_id: string;
  lora_path: string;
  output_name: string;
}

export interface MergeStatus {
  status: string;
  message: string;
  progress: number;
  output_path?: string;
}
