import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiClient, chatInference, inference } from '../services/api';

describe('inference API contracts', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends generate options in the backend request schema', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { response: 'ok' } });

    await inference({
      modelId: 'base-model',
      prompt: 'hello',
      maxTokens: 128,
      temperature: 0.2,
      backend: 'huggingface',
      loraAdapter: 'C:/outputs/adapter',
    });

    expect(post).toHaveBeenCalledWith('/inference/generate', {
      model: 'base-model',
      prompt: 'hello',
      lora_adapter: 'C:/outputs/adapter',
      options: {
        max_tokens: 128,
        temperature: 0.2,
        backend: 'huggingface',
        lora_adapter: 'C:/outputs/adapter',
      },
    });
  });

  it('nests chat generation settings under options', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { message: {} } });

    await chatInference(
      'deployed-alias',
      [{ role: 'user', content: 'hello' }],
      {
        maxTokens: 256,
        temperature: 0.3,
        backend: 'huggingface',
        loraAdapter: 'C:/outputs/adapter',
      },
    );

    expect(post).toHaveBeenCalledWith('/inference/chat', {
      model_id: 'deployed-alias',
      messages: [{ role: 'user', content: 'hello' }],
      options: {
        max_tokens: 256,
        temperature: 0.3,
        backend: 'huggingface',
        lora_adapter: 'C:/outputs/adapter',
      },
    });
  });
});
