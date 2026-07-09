/**
 * Inference performance service layer.
 * Centralizes /inference/performance/* metrics & suggestions HTTP calls
 * through the shared apiClient instance.
 *
 * Note: These endpoints (`/metrics`, `/suggestions`) are distinct from the
 * `/inference/performance` and `/inference/performance/recommendations`
 * helpers exposed in api.ts — do not mix them up.
 */
import { apiClient } from './api';

export const getPerformanceMetrics = async <T = Record<string, unknown>>(): Promise<T> => {
  const response = await apiClient.get('/inference/performance/metrics');
  return response.data;
};

export const getPerformanceSuggestions = async <T = unknown[] | Record<string, unknown>>(): Promise<T> => {
  const response = await apiClient.get('/inference/performance/suggestions');
  return response.data;
};
