/**
 * Context understanding service layer.
 * Centralizes all /context/understanding/* HTTP calls through the shared apiClient instance.
 */
import { apiClient } from './api';

export type ContextUnderstandingStatusResult = Record<string, unknown>;

export const getContextUnderstandingStatus = async (): Promise<ContextUnderstandingStatusResult> => {
  const response = await apiClient.get('/context/understanding/status');
  return response.data;
};

export const processContextUnderstanding = async <T = Record<string, unknown>>(
  payload: Record<string, unknown>,
): Promise<T> => {
  const response = await apiClient.post('/context/understanding/process', payload);
  return response.data;
};

export const enhanceContext = async <T = Record<string, unknown>>(
  payload: Record<string, unknown>,
): Promise<T> => {
  const response = await apiClient.post('/context/understanding/enhance', payload);
  return response.data;
};

export const summarizeContext = async <T = Record<string, unknown>>(
  payload: Record<string, unknown>,
): Promise<T> => {
  const response = await apiClient.post('/context/understanding/summarize', payload);
  return response.data;
};

export const manageContextWindow = async <T = Record<string, unknown>>(
  payload: Record<string, unknown>,
): Promise<T> => {
  const response = await apiClient.post('/context/understanding/window', payload);
  return response.data;
};
