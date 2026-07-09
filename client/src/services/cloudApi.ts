/**
 * Cloud provider API key management service layer.
 * Centralizes all /cloud/* HTTP calls through the shared apiClient instance.
 */
import { apiClient } from './api';

export interface CloudApiKeyPayload {
  provider: string;
  api_key?: string;
  group_id?: string;
  base_url?: string;
  name?: string;
  note?: string;
  official_url?: string;
  interface_format?: string;
  default_model?: string;
  models?: string[];
}

export interface CloudProviderTestParams {
  base_url?: string;
  group_id?: string;
}

export interface CloudProviderTestResult {
  success?: boolean;
  message?: string;
  detail?: string;
  [key: string]: unknown;
}

export const saveCloudApiKey = async (payload: CloudApiKeyPayload): Promise<Record<string, unknown>> => {
  const response = await apiClient.post('/cloud/api-keys', payload);
  return response.data;
};

export const testCloudProvider = async (
  provider: string,
  params?: CloudProviderTestParams,
): Promise<CloudProviderTestResult> => {
  const response = await apiClient.post(`/cloud/test/${provider}`, null, { params });
  return response.data;
};

export const deleteCloudApiKey = async (provider: string): Promise<void> => {
  await apiClient.delete(`/cloud/api-keys/${provider}`);
};
