/**
 * 数据集相关类型定义
 */

export interface DatasetInfo {
  id: string;
  name: string;
  path: string;
  size: number;
  size_formatted: string;
  format: string;
  samples: number;
  created_at: string;
  updated_at?: string;
  file_hash?: string;
  statistics?: DatasetStatistics;
}

export interface DatasetStatistics {
  total_samples: number;
  avg_message_length: number;
  avg_turns: number;
  role_distribution: Record<string, number>;
  message_length_distribution: Record<string, string>;
  sample_length_distribution: Record<string, number>;
}

export interface DatasetPreview {
  total_samples: number;
  preview: Array<Record<string, unknown>>;
  limit: number;
}
