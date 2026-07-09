/**
 * SWIFT framework service layer.
 * Centralizes /training/check-swift HTTP calls through the shared apiClient instance.
 */
import { apiClient } from './api';

export const checkSwift = async <T = Record<string, unknown>>(): Promise<T> => {
  const response = await apiClient.get('/training/check-swift');
  return response.data;
};
