/**
 * Project context management service layer.
 * Centralizes all /context/* project indexing HTTP calls through the shared apiClient instance.
 */
import { apiClient } from './api';

export interface ProjectContextScanPayload {
  project_path: string;
}

export interface ProjectContextIndexPayload {
  project_path: string;
  force_reindex?: boolean;
}

export interface ProjectContextRemovePayload {
  project_path: string;
}

export interface ProjectContextListResult {
  success?: boolean;
  projects?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface ProjectContextScanResult {
  success?: boolean;
  message?: string;
  [key: string]: unknown;
}

export interface ProjectContextIndexSummary {
  files_indexed?: number;
  symbols_found?: number;
  [key: string]: unknown;
}

export interface ProjectContextIndexResult {
  success?: boolean;
  message?: string;
  summary?: ProjectContextIndexSummary;
  [key: string]: unknown;
}

export interface ProjectContextRemoveResult {
  success?: boolean;
  message?: string;
  [key: string]: unknown;
}

export const getProjectContexts = async (): Promise<ProjectContextListResult> => {
  const response = await apiClient.get('/context/projects');
  return response.data;
};

export const scanProject = async (payload: ProjectContextScanPayload): Promise<ProjectContextScanResult> => {
  const response = await apiClient.post('/context/scan', payload);
  return response.data;
};

export const indexProject = async (payload: ProjectContextIndexPayload): Promise<ProjectContextIndexResult> => {
  const response = await apiClient.post('/context/index', payload);
  return response.data;
};

export const removeProjectContext = async (
  payload: ProjectContextRemovePayload,
): Promise<ProjectContextRemoveResult> => {
  const response = await apiClient.post('/context/remove', payload);
  return response.data;
};
