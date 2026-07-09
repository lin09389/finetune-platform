/**
 * Chat share service layer.
 * Centralizes /chat/share/* HTTP calls through the shared apiClient instance.
 */
import { apiClient } from './api';

export const getSharedChat = async <T = Record<string, unknown>>(shareId: string): Promise<T> => {
  const response = await apiClient.get(`/chat/share/${shareId}`);
  return response.data;
};

export const getSharedChatMarkdown = async (shareId: string): Promise<string> => {
  const response = await apiClient.get(`/chat/share/${shareId}/markdown`, {
    responseType: 'text',
  });
  return response.data;
};
