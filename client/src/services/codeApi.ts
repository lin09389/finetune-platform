/**
 * Code execution service layer.
 * Centralizes /code/* HTTP calls through the shared apiClient instance.
 */
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from './api';

export interface ExecuteCodePayload {
  code: string;
  language: string;
  timeout?: number;
  memory_limit_mb?: number;
  stdin?: string | null;
}

export const executeCode = async <T = Record<string, unknown>>(
  payload: ExecuteCodePayload,
  config?: AxiosRequestConfig,
): Promise<T> => {
  const response = await apiClient.post('/code/execute', payload, config);
  return response.data;
};
