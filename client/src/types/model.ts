/**
 * 模型相关类型定义
 */

export interface ModelInfo {
  id: string;
  name: string;
  path: string;
  size: number;
  size_formatted: string;
  type: string;
  quantized?: number;
  created_at: string;
  updated_at?: string;
  config?: Record<string, unknown>;
}

export interface ModelDownloadRequest {
  model_name: string;
  revision?: string;
  quantize?: number;
  use_safetensors?: boolean;
}

export interface DownloadStatus {
  is_downloading: boolean;
  model_name: string;
  progress: number;
  message: string;
  error: string | null;
}

export interface ModelStats {
  total_models: number;
  total_size: number;
  total_size_formatted: string;
  quantized_models: number;
  base_models: number;
}
