/**
 * Knowledge base (RAG) service layer.
 * Centralizes all /knowledge/* HTTP calls through the shared apiClient instance.
 */
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from './api';

export interface KnowledgeCollection {
  name: string;
  count?: number;
}

export interface KnowledgeCollectionsResponse {
  collections: KnowledgeCollection[];
}

export interface EmbedderStatus {
  loaded?: boolean;
  dimension?: number;
  model?: string;
  [key: string]: unknown;
}

export interface UploadTaskStatus {
  task_id: string;
  status: string;
  progress?: number;
  message?: string;
  error?: string;
  result?: { file_name?: string; chunk_count?: number };
}

export const getKnowledgeCollections = async (
  config?: AxiosRequestConfig,
): Promise<KnowledgeCollectionsResponse> => {
  const response = await apiClient.get('/knowledge/collections', config);
  return response.data;
};

export const getKnowledgeEmbedderStatus = async (
  config?: AxiosRequestConfig,
): Promise<EmbedderStatus> => {
  const response = await apiClient.get('/knowledge/embedder/status', config);
  return response.data;
};

export const getKnowledgeCollection = async <T = Record<string, unknown>>(
  collectionId: string,
  config?: AxiosRequestConfig,
): Promise<T> => {
  const response = await apiClient.get(`/knowledge/collections/${collectionId}`, config);
  return response.data;
};

export const preloadKnowledgeEmbedder = async (
  config?: AxiosRequestConfig,
): Promise<{ dimension?: number; [key: string]: unknown }> => {
  const response = await apiClient.post('/knowledge/embedder/preload', undefined, config);
  return response.data;
};

export const uploadKnowledgeDocumentAsync = async (
  formData: FormData,
  config?: AxiosRequestConfig,
): Promise<UploadTaskStatus> => {
  const response = await apiClient.post('/knowledge/upload/async', formData, config);
  return response.data;
};

export const getKnowledgeUploadStatus = async (taskId: string): Promise<UploadTaskStatus> => {
  const response = await apiClient.get(`/knowledge/upload/status/${taskId}`);
  return response.data;
};

export const deleteKnowledgeDocument = async (
  collectionId: string,
  docId: string,
): Promise<void> => {
  await apiClient.delete(`/knowledge/collections/${collectionId}/documents/${docId}`);
};
