/**
 * OCR service layer.
 * Centralizes /ocr HTTP calls through the shared apiClient instance.
 */
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from './api';

export interface OcrRequestPayload {
  image_base64: string;
}

export const runOcr = async <T = Record<string, unknown>>(
  payload: OcrRequestPayload,
  config?: AxiosRequestConfig,
): Promise<T> => {
  const response = await apiClient.post('/ocr', payload, config);
  return response.data;
};
