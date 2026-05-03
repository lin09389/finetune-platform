import { useCallback, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../../services/api';
import { persistChatRunToSession } from '../../services/chatSessionApi';
import { generateTitleCloud, generateTitleLocal } from '../../services/api';
import { useChatStore } from '../../store/chatStore';
import type {
  KnowledgeSource,
  PlaygroundAttachment,
  PlaygroundRunMetrics,
  RetrievalInfo,
} from '../../types';

interface StreamConfig {
  onChunk?: (chunk: string, fullContent: string) => void;
  onComplete?: (content: string, metadata?: StreamMetadata) => void;
  onError?: (error: string) => void;
  onStatusChange?: (status: StreamState['status']) => void;
}

interface StreamState {
  status: 'idle' | 'connecting' | 'streaming' | 'completed' | 'error' | 'stopped';
}

export interface StreamMetadata {
  knowledgeSources?: KnowledgeSource[];
  retrievalInfo?: RetrievalInfo;
  memoryContext?: {
    retrieved: boolean;
    sources_count: number;
    context_preview: string;
  };
  unifiedContext?: {
    total_sources: number;
    memory_count: number;
    knowledge_count: number;
    project_count?: number;
    retrieval_time: number;
  };
  rawResponse?: unknown;
  runMetrics?: PlaygroundRunMetrics;
}

export interface ChatSendPayload {
  prompt: string;
  systemPrompt?: string;
  responseFormat?: 'text' | 'json';
  attachments?: PlaygroundAttachment[];
  knowledgeOverride?: { enabled: boolean; collectionId?: string };
  memoryOverride?: { enabled: boolean };
  parameterOverrides?: {
    temperature?: number;
    topP?: number;
    maxTokens?: number;
    backend?: 'ollama' | 'huggingface' | 'cloud';
    modelId?: string;
  };
}

export interface ChatRunResult {
  content: string;
  metadata?: StreamMetadata;
}

interface CloudConfig {
  provider: string;
  apiKey?: string;
  keyId?: string;
  model: string;
  groupId?: string;
  baseUrl?: string;
}

const STREAM_IDLE_TIMEOUT_MS = 45000;
const OLLAMA_PREFLIGHT_TIMEOUT_MS = 4000;
const CLOUD_LARGE_DELTA_THRESHOLD = 48;
const CLOUD_SMOOTH_CHUNK_SIZE = 3;
const CLOUD_SMOOTH_DELAY_MS = 14;

export function splitDeltaForDisplay(delta: string): string[] {
  const chars = Array.from(delta);
  if (chars.length <= CLOUD_LARGE_DELTA_THRESHOLD) {
    return [delta];
  }

  const chunks: string[] = [];
  for (let index = 0; index < chars.length; index += CLOUD_SMOOTH_CHUNK_SIZE) {
    chunks.push(chars.slice(index, index + CLOUD_SMOOTH_CHUNK_SIZE).join(''));
  }
  return chunks;
}

function waitForSmoothDelay(signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.reject(new DOMException('Aborted', 'AbortError'));
  }

  return new Promise((resolve, reject) => {
    const abortHandler = () => {
      clearTimeout(timeoutId);
      signal.removeEventListener('abort', abortHandler);
      reject(new DOMException('Aborted', 'AbortError'));
    };

    const timeoutId = setTimeout(() => {
      signal.removeEventListener('abort', abortHandler);
      resolve();
    }, CLOUD_SMOOTH_DELAY_MS);

    signal.addEventListener('abort', abortHandler, { once: true });
  });
}

function toRequestAttachments(attachments: PlaygroundAttachment[] = []) {
  return attachments.map((attachment) => ({
    name: attachment.name,
    type: attachment.type,
    mime_type: attachment.mimeType,
    size: attachment.size,
    content: attachment.content,
    preview_url: attachment.previewUrl,
  }));
}

function mergeMetadata(current: StreamMetadata, incoming: Record<string, unknown>): StreamMetadata {
  const knowledgeSources = Array.isArray(incoming.knowledge_sources)
    ? (incoming.knowledge_sources as KnowledgeSource[])
    : current.knowledgeSources;

  const retrievalInfo =
    (incoming.retrieval_info as RetrievalInfo | undefined) ?? current.retrievalInfo;

  const memoryContext =
    (incoming.memory_context as StreamMetadata['memoryContext'] | undefined) ??
    current.memoryContext;

  const unifiedContext =
    (incoming.unified_context as StreamMetadata['unifiedContext'] | undefined) ??
    current.unifiedContext;

  const runMetrics: PlaygroundRunMetrics = {
    ...(current.runMetrics || {}),
    model: (incoming.model as string | undefined) ?? current.runMetrics?.model,
    backend: (incoming.backend as string | undefined) ?? current.runMetrics?.backend,
    duration_ms:
      (incoming.duration_ms as number | undefined) ??
      (current.runMetrics?.duration_ms as number | undefined),
    prompt_tokens:
      (incoming.prompt_tokens as number | undefined) ??
      (current.runMetrics?.prompt_tokens as number | undefined),
    completion_tokens:
      (incoming.completion_tokens as number | undefined) ??
      (current.runMetrics?.completion_tokens as number | undefined),
    total_tokens:
      (incoming.total_tokens as number | undefined) ??
      (current.runMetrics?.total_tokens as number | undefined),
  };

  return {
    ...current,
    knowledgeSources,
    retrievalInfo,
    memoryContext,
    unifiedContext,
    runMetrics: Object.values(runMetrics).some((value) => value !== undefined)
      ? runMetrics
      : undefined,
    rawResponse: incoming.raw_response ?? current.rawResponse,
  };
}

async function streamSse(
  url: string,
  body: Record<string, unknown>,
  signal: AbortSignal,
  onDelta: (delta: string) => void | Promise<void>,
): Promise<ChatRunResult> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detail =
      (errorData as { detail?: string }).detail ||
      (errorData as { error?: string }).error ||
      `Request failed: ${response.status}`;
    throw new Error(detail);
  }

  if (!response.body) {
    throw new Error('Stream is not available from server response.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let content = '';
  let metadata: StreamMetadata = {};
  let lastYieldTime = performance.now();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const records = buffer.split('\n\n');
    buffer = records.pop() || '';

    for (const record of records) {
      const dataLines = record
        .split(/\r?\n/)
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart());
      if (!dataLines.length) continue;

      const dataText = dataLines.join('\n');
      if (!dataText || dataText === '[DONE]') continue;

      let parsed: Record<string, unknown> | null = null;
      try {
        parsed = JSON.parse(dataText) as Record<string, unknown>;
      } catch {
        parsed = { type: 'delta', content: dataText };
      }

      if (!parsed) continue;

      if (typeof parsed.error === 'string' && parsed.error) {
        throw new Error(parsed.error);
      }

      if (parsed.type === 'metadata') {
        metadata = mergeMetadata(metadata, parsed);
        continue;
      }

      if (parsed.type === 'done') {
        continue;
      }

      const delta =
        typeof parsed.content === 'string'
          ? parsed.content
          : typeof parsed.delta === 'string'
            ? parsed.delta
            : '';
      if (!delta) continue;

      content += delta;
      await onDelta(delta);
    }

    // Yield to the browser's event loop if we've been processing synchronously for too long
    // This prevents the main thread from blocking and ensures requestAnimationFrame fires
    // for progressive rendering during high-speed local streams or coalesced network packets.
    if (performance.now() - lastYieldTime > 16) {
      await new Promise((resolve) => setTimeout(resolve, 0));
      lastYieldTime = performance.now();
    }
  }

  return { content, metadata: Object.keys(metadata).length ? metadata : undefined };
}

async function checkOllamaAvailability(): Promise<boolean> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), OLLAMA_PREFLIGHT_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/inference/ollama/status`, {
      signal: controller.signal,
      headers: { 'Cache-Control': 'no-cache' },
    });
    if (!response.ok) return false;
    const data = (await response.json()) as { available?: boolean; running?: boolean };
    return Boolean(data.available || data.running);
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

export function useChatStream(config: StreamConfig = {}) {
  const isStreaming = useChatStore((state) => state.isStreaming);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const sendMessage = useCallback(
    async (payload: ChatSendPayload): Promise<ChatRunResult | undefined> => {
      const store = useChatStore.getState();
      const prompt = payload.prompt.trim();
      if (!prompt) return undefined;

      const requestedBackend = payload.parameterOverrides?.backend || store.settings.backend;
      if (requestedBackend === 'ollama') {
        const ollamaReady = await checkOllamaAvailability();
        if (!ollamaReady) {
          const errorMessage =
            'Ollama 当前不可用，请先启动 Ollama 服务并确认模型可用，或切换后端后重试。';
          store.setError(errorMessage);
          config.onStatusChange?.('error');
          config.onError?.(errorMessage);
          return undefined;
        }
      }

      let sessionId = store.currentSessionId;
      const isNewSession = !sessionId || store.messages.length === 0;
      if (!sessionId) {
        const session = await store.createSession();
        sessionId = session.id;
      }

      const userMessageId = store.addMessage({
        role: 'user',
        content: prompt,
        attachments: payload.attachments?.length ? payload.attachments : undefined,
      });
      const assistantMessageId = store.addMessage({
        role: 'assistant',
        content: '',
        isLoading: true,
      });

      const currentState = useChatStore.getState();
      const messages = currentState.messages.map((message) => ({
        role: message.role,
        content: message.content,
      }));
      const attachments = payload.attachments ?? currentState.attachments;

      const requestBody = {
        model: payload.parameterOverrides?.modelId || currentState.settings.modelId,
        messages,
        stream: true,
        format: payload.responseFormat || currentState.settings.responseFormat,
        response_format: payload.responseFormat || currentState.settings.responseFormat,
        system_prompt: payload.systemPrompt || currentState.settings.systemPrompt,
        options: {
          backend: payload.parameterOverrides?.backend || currentState.settings.backend,
          temperature: payload.parameterOverrides?.temperature ?? currentState.settings.temperature,
          top_p: payload.parameterOverrides?.topP ?? currentState.settings.topP,
          max_tokens: payload.parameterOverrides?.maxTokens ?? currentState.settings.maxTokens,
        },
        attachments: toRequestAttachments(attachments),
        knowledge: {
          use_knowledge: payload.knowledgeOverride?.enabled ?? currentState.settings.useKnowledge,
          collection_id:
            payload.knowledgeOverride?.collectionId ?? currentState.settings.knowledgeCollection,
          auto_retrieve: currentState.settings.autoRetrieve,
          include_sources: true,
        },
        memory: {
          enabled: payload.memoryOverride?.enabled ?? currentState.settings.useMemory,
          auto_extract: true,
          auto_retrieve: currentState.settings.autoRetrieve,
        },
        session: {
          session_id: sessionId,
          user_id: 'default',
        },
      };

      const controller = new AbortController();
      abortRef.current = controller;
      let timeoutTriggered = false;
      let timeoutId: ReturnType<typeof setTimeout> | null = null;

      const clearStreamTimeout = () => {
        if (timeoutId) {
          clearTimeout(timeoutId);
          timeoutId = null;
        }
      };

      const refreshStreamTimeout = () => {
        clearStreamTimeout();
        timeoutId = setTimeout(() => {
          timeoutTriggered = true;
          controller.abort();
        }, STREAM_IDLE_TIMEOUT_MS);
      };

      store.setError(null);
      store.setIsLoading(true);
      store.startStreaming(assistantMessageId);
      store.setStreamState({ status: 'connecting', content: '' });
      config.onStatusChange?.('connecting');
      refreshStreamTimeout();

      let fullContent = '';
      let flushPending = false;
      let frameId: number | null = null;
      let flushTimeoutId: ReturnType<typeof setTimeout> | null = null;
      let lastFlushTime = 0;

      const flushUpdate = () => {
        const activeStore = useChatStore.getState();
        activeStore.setStreamState({ status: 'streaming' });
        activeStore.updateStreamingContent(fullContent);
        flushPending = false;
        lastFlushTime = Date.now();
      };

      try {
        const result = await streamSse(
          `${API_BASE_URL}/inference/chat/stream`,
          requestBody,
          controller.signal,
          (delta) => {
            fullContent += delta;
            refreshStreamTimeout();

            if (!flushPending) {
              flushPending = true;
              const now = Date.now();
              const timeSinceLastFlush = now - lastFlushTime;
              const throttleMs = 32; // Throttle to ~30fps to prevent ReactMarkdown from freezing the main thread

              if (timeSinceLastFlush >= throttleMs) {
                frameId = requestAnimationFrame(flushUpdate);
              } else {
                flushTimeoutId = setTimeout(() => {
                  frameId = requestAnimationFrame(flushUpdate);
                }, throttleMs - timeSinceLastFlush);
              }
            }

            config.onStatusChange?.('streaming');
            config.onChunk?.(delta, fullContent);
          },
        );
        if (flushTimeoutId) clearTimeout(flushTimeoutId);
        if (frameId) cancelAnimationFrame(frameId);
        flushUpdate();

        const assistantMetadata = {
          knowledge_sources: result.metadata?.knowledgeSources,
          retrieval_info: result.metadata?.retrievalInfo,
          memory_context: result.metadata?.memoryContext,
          unified_context: result.metadata?.unifiedContext,
          raw_response: result.metadata?.rawResponse,
          run_metrics: result.metadata?.runMetrics,
        };

        const successStore = useChatStore.getState();
        successStore.updateMessage(assistantMessageId, {
          content: result.content,
          isLoading: false,
          ...assistantMetadata,
        });
        successStore.completeStreaming();
        successStore.setIsLoading(false);
        successStore.clearAttachments();
        successStore.setStreamState({ status: 'completed' });
        config.onStatusChange?.('completed');
        config.onComplete?.(result.content, result.metadata);

        if (sessionId) {
          try {
            const persisted = await persistChatRunToSession(sessionId, prompt, result.content, {
              userMetadata: {
                message_id: userMessageId,
              },
              assistantMetadata,
            });
            const persistedStore = useChatStore.getState();
            persistedStore.updateMessage(userMessageId, {
              id: persisted.userMessage.id,
              timestamp: persisted.userMessage.timestamp,
            });
            persistedStore.updateMessage(assistantMessageId, {
              id: persisted.assistantMessage.id,
              timestamp: persisted.assistantMessage.timestamp,
            });
            await persistedStore.loadSessions().catch(() => undefined);

            if (isNewSession) {
              const combinedContent = `用户提问: ${prompt}\n\nAI回复: ${result.content}`;
              generateTitleLocal(
                payload.parameterOverrides?.modelId || currentState.settings.modelId,
                payload.parameterOverrides?.backend || currentState.settings.backend,
                combinedContent
              ).then(title => {
                if (title) persistedStore.updateSessionTitle(sessionId, title);
              }).catch(e => console.error('Failed to generate local title:', e));
            }
          } catch (persistError) {
            const message =
              persistError instanceof Error ? persistError.message : '历史记录保存失败';
            const persistStore = useChatStore.getState();
            persistStore.setError(`对话已生成，但历史记录保存失败：${message}`);
            config.onError?.(`对话已生成，但历史记录保存失败：${message}`);
          }
        }

        return result;
      } catch (error) {
        const failedStore = useChatStore.getState();
        const aborted = controller.signal.aborted;
        const errorMessage = timeoutTriggered
          ? '模型响应超时，请检查 Ollama 服务状态或切换后端后重试。'
          : aborted
            ? '已停止生成。'
            : error instanceof Error
              ? error.message
              : '请求失败';

        failedStore.updateMessage(assistantMessageId, {
          content: fullContent || errorMessage,
          isLoading: false,
        });
        if (aborted && !timeoutTriggered) {
          failedStore.stopStreaming();
          failedStore.setStreamState({ status: 'stopped' });
          config.onStatusChange?.('stopped');
        } else {
          failedStore.stopStreaming();
          failedStore.setStreamState({ status: 'error', error: errorMessage });
          failedStore.setError(errorMessage);
          config.onStatusChange?.('error');
          config.onError?.(errorMessage);
        }
        failedStore.setIsLoading(false);
        return undefined;
      } finally {
        clearStreamTimeout();
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [config],
  );

  const sendCloudMessage = useCallback(
    async (
      payload: ChatSendPayload,
      cloudConfig: CloudConfig,
    ): Promise<ChatRunResult | undefined> => {
      const store = useChatStore.getState();
      const prompt = payload.prompt.trim();
      if (!prompt) return undefined;

      let sessionId = store.currentSessionId;
      const isNewSession = !sessionId || store.messages.length === 0;
      if (!sessionId) {
        const session = await store.createSession();
        sessionId = session.id;
      }

      const userMessageId = store.addMessage({
        role: 'user',
        content: prompt,
        attachments: payload.attachments?.length ? payload.attachments : undefined,
      });
      const assistantMessageId = store.addMessage({
        role: 'assistant',
        content: '',
        isLoading: true,
      });

      const currentState = useChatStore.getState();
      const messages = currentState.messages.map((message) => ({
        role: message.role,
        content: message.content,
      }));
      const attachments = payload.attachments ?? currentState.attachments;

      const requestBody = {
        provider: cloudConfig.provider,
        model: cloudConfig.model,
        messages,
        stream: true,
        api_key: cloudConfig.apiKey,
        key_id: cloudConfig.keyId,
        group_id: cloudConfig.groupId,
        base_url: cloudConfig.baseUrl,
        temperature: payload.parameterOverrides?.temperature ?? currentState.settings.temperature,
        max_tokens: payload.parameterOverrides?.maxTokens ?? currentState.settings.maxTokens,
        system_prompt: payload.systemPrompt || currentState.settings.systemPrompt,
        response_format: payload.responseFormat || currentState.settings.responseFormat,
        attachments: toRequestAttachments(attachments),
        knowledge: {
          use_knowledge: payload.knowledgeOverride?.enabled ?? currentState.settings.useKnowledge,
          collection_id:
            payload.knowledgeOverride?.collectionId ?? currentState.settings.knowledgeCollection,
          auto_retrieve: currentState.settings.autoRetrieve,
        },
        memory: {
          enabled: payload.memoryOverride?.enabled ?? currentState.settings.useMemory,
          auto_extract: true,
          auto_retrieve: currentState.settings.autoRetrieve,
        },
        session: {
          session_id: sessionId,
          user_id: 'default',
        },
      };

      const controller = new AbortController();
      abortRef.current = controller;
      let timeoutTriggered = false;
      let timeoutId: ReturnType<typeof setTimeout> | null = null;

      const clearStreamTimeout = () => {
        if (timeoutId) {
          clearTimeout(timeoutId);
          timeoutId = null;
        }
      };

      const refreshStreamTimeout = () => {
        clearStreamTimeout();
        timeoutId = setTimeout(() => {
          timeoutTriggered = true;
          controller.abort();
        }, STREAM_IDLE_TIMEOUT_MS);
      };

      store.setError(null);
      store.setIsLoading(true);
      store.startStreaming(assistantMessageId);
      store.setStreamState({ status: 'connecting', content: '' });
      config.onStatusChange?.('connecting');
      refreshStreamTimeout();

      let fullContent = '';
      let flushPending = false;
      let frameId: number | null = null;
      let flushTimeoutId: ReturnType<typeof setTimeout> | null = null;
      let lastFlushTime = 0;

      const flushUpdate = () => {
        const activeStore = useChatStore.getState();
        activeStore.setStreamState({ status: 'streaming' });
        activeStore.updateStreamingContent(fullContent);
        flushPending = false;
        lastFlushTime = Date.now();
      };

      try {
        const result = await streamSse(
          `${API_BASE_URL}/cloud/chat/stream`,
          requestBody,
          controller.signal,
          async (delta) => {
            const displayChunks = splitDeltaForDisplay(delta);

            for (let index = 0; index < displayChunks.length; index += 1) {
              if (controller.signal.aborted) {
                throw new DOMException('Aborted', 'AbortError');
              }

              const displayChunk = displayChunks[index] ?? '';
              if (!displayChunk) continue;
              fullContent += displayChunk;
              refreshStreamTimeout();

              if (!flushPending) {
                flushPending = true;
                const now = Date.now();
                const timeSinceLastFlush = now - lastFlushTime;
                const throttleMs = 32; // Throttle to ~30fps to prevent ReactMarkdown from freezing the main thread

                if (timeSinceLastFlush >= throttleMs) {
                  frameId = requestAnimationFrame(flushUpdate);
                } else {
                  flushTimeoutId = setTimeout(() => {
                    frameId = requestAnimationFrame(flushUpdate);
                  }, throttleMs - timeSinceLastFlush);
                }
              }

              config.onStatusChange?.('streaming');
              config.onChunk?.(displayChunk, fullContent);

              if (displayChunks.length > 1 && index < displayChunks.length - 1) {
                await waitForSmoothDelay(controller.signal);
              }
            }
          },
        );
        if (flushTimeoutId) clearTimeout(flushTimeoutId);
        if (frameId) cancelAnimationFrame(frameId);
        flushUpdate();

        const assistantMetadata = {
          knowledge_sources: result.metadata?.knowledgeSources,
          retrieval_info: result.metadata?.retrievalInfo,
          memory_context: result.metadata?.memoryContext,
          unified_context: result.metadata?.unifiedContext,
          raw_response: result.metadata?.rawResponse,
          run_metrics: result.metadata?.runMetrics,
        };

        const successStore = useChatStore.getState();
        successStore.updateMessage(assistantMessageId, {
          content: result.content,
          isLoading: false,
          ...assistantMetadata,
        });
        successStore.completeStreaming();
        successStore.setIsLoading(false);
        successStore.clearAttachments();
        successStore.setStreamState({ status: 'completed' });
        config.onStatusChange?.('completed');
        config.onComplete?.(result.content, result.metadata);

        if (sessionId) {
          try {
            const persisted = await persistChatRunToSession(sessionId, prompt, result.content, {
              userMetadata: {
                message_id: userMessageId,
              },
              assistantMetadata,
            });
            const persistedStore = useChatStore.getState();
            persistedStore.updateMessage(userMessageId, {
              id: persisted.userMessage.id,
              timestamp: persisted.userMessage.timestamp,
            });
            persistedStore.updateMessage(assistantMessageId, {
              id: persisted.assistantMessage.id,
              timestamp: persisted.assistantMessage.timestamp,
            });
            await persistedStore.loadSessions().catch(() => undefined);

            if (isNewSession) {
              const combinedContent = `用户提问: ${prompt}\n\nAI回复: ${result.content}`;
              generateTitleCloud(combinedContent, {
                provider: cloudConfig.provider,
                model: cloudConfig.model,
                apiKey: cloudConfig.apiKey,
                keyId: cloudConfig.keyId,
                groupId: cloudConfig.groupId,
                baseUrl: cloudConfig.baseUrl,
              }).then(title => {
                if (title) persistedStore.updateSessionTitle(sessionId, title);
              }).catch(e => console.error('Failed to generate cloud title:', e));
            }
          } catch (persistError) {
            const message =
              persistError instanceof Error ? persistError.message : '历史记录保存失败';
            const persistStore = useChatStore.getState();
            persistStore.setError(`对话已生成，但历史记录保存失败：${message}`);
            config.onError?.(`对话已生成，但历史记录保存失败：${message}`);
          }
        }

        return result;
      } catch (error) {
        const failedStore = useChatStore.getState();
        const aborted = controller.signal.aborted;
        const errorMessage = timeoutTriggered
          ? '云端响应超时，请检查网络或稍后重试。'
          : aborted
            ? '已停止生成。'
            : error instanceof Error
              ? error.message
              : '请求失败';

        failedStore.updateMessage(assistantMessageId, {
          content: fullContent || errorMessage,
          isLoading: false,
        });
        if (aborted && !timeoutTriggered) {
          failedStore.stopStreaming();
          failedStore.setStreamState({ status: 'stopped' });
          config.onStatusChange?.('stopped');
        } else {
          failedStore.stopStreaming();
          failedStore.setStreamState({ status: 'error', error: errorMessage });
          failedStore.setError(errorMessage);
          config.onStatusChange?.('error');
          config.onError?.(errorMessage);
        }
        failedStore.setIsLoading(false);
        return undefined;
      } finally {
        clearStreamTimeout();
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [config],
  );

  return {
    sendMessage,
    sendCloudMessage,
    stop,
    isStreaming,
  };
}
