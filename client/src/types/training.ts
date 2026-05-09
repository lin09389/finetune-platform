/**
 * 训练相关类型定义
 */

export type TrainingStatus =
  | 'idle'
  | 'loading'
  | 'training'
  | 'running'
  | 'stopping'
  | 'completed'
  | 'failed'
  | 'stopped';

export interface TrainingProgress {
  epoch: number;
  step: number;
  total_steps: number;
  loss: number;
  lr: number;
  vram_used: number;
  elapsed_time: number;
  eta: number;
  status: TrainingStatus;
  message: string;
  queue_position?: number;
  estimated_wait_seconds?: number;
  error_code?: string;
  error_category?: string;
  actionable_suggestions?: string[];
  // 扩展观测字段
  grad_norm?: number | null;
  speed?: number;
  samples_per_sec?: number;
  current_phase?: string;
  phase_durations?: Record<string, number>;
  retry_count?: number;
}

export interface TrainingConfig {
  model_id: string;
  dataset_id: string;
  method: 'qlora' | 'lora';
  rank: number;
  alpha: number;
  learning_rate: number;
  epochs: number;
  batch_size: number;
  gradient_accumulation: number;
  max_seq_length: number;
  warmup_steps: number;
  save_steps: number;
  logging_steps: number;
  quantization: number;
  resume_from_checkpoint?: string;
  resume_from_adapter?: string;
}

export interface TrainingRecord {
  id: string;
  model_name: string;
  dataset_name: string;
  method: string;
  status: string;
  start_time: string;
  end_time?: string;
  config: TrainingConfig;
  output_path: string;
  checkpoint_path?: string;
}

export interface TrainingStatusResponse {
  is_training: boolean;
  record: TrainingRecord | null;
  progress: TrainingProgress;
  active_tasks: number;
}

export interface Checkpoint {
  name: string;
  path: string;
  step: number;
  created: string;
}
