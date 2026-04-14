import { useCallback, useEffect, useRef } from 'react'
import { API_BASE_URL } from '../../services/api'
import { persistChatRunToSession } from '../../services/chatSessionApi'
import { useChatStore } from '../../store/chatStore'
import type { KnowledgeSource, PlaygroundAttachment, PlaygroundRunMetrics, RetrievalInfo } from '../../types'

interface StreamConfig {
  onChunk?: (chunk: string, fullContent: string) => void
  onComplete?: (content: string, metadata?: StreamMetadata) => void
  onError?: (error: string) => void
  onStatusChange?: (status: StreamState['status']) => void
}

interface StreamState {
  status: 'idle' | 'connecting' | 'streaming' | 'completed' | 'error' | 'stopped'
}

export interface StreamMetadata {
  knowledgeSources?: KnowledgeSource[]
  retrievalInfo?: RetrievalInfo
  memoryContext?: {
    retrieved: boolean
    sources_count: number
    context_preview: string
  }
  unifiedContext?: {
    total_sources: number
    memory_count: number
    knowledge_count: number
    project_count?: number
    retrieval_time: number
  }
  rawResponse?: unknown
  runMetrics?: PlaygroundRunMetrics
}

export interface ChatSendPayload {
  prompt: string
  systemPrompt?: string
  responseFormat?: 'text' | 'json'
  attachments?: PlaygroundAttachment[]
  knowledgeOverride?: { enabled: boolean; collectionId?: string }
  memoryOverride?: { enabled: boolean }
  parameterOverrides?: {
    temperature?: number
    topP?: number
    maxTokens?: number
    backend?: 'ollama' | 'huggingface' | 'cloud'
    modelId?: string
  }
}

export interface ChatRunResult {
  content: string
  metadata?: StreamMetadata
}

interface CloudConfig {
  provider: string
  apiKey?: string
  keyId?: string
  model: string
  groupId?: string
  baseUrl?: string
}

function toRequestAttachments(attachments: PlaygroundAttachment[] = []) {
  return attachments.map((attachment) => ({
    name: attachment.name,
    type: attachment.type,
    mime_type: attachment.mimeType,
    size: attachment.size,
    content: attachment.content,
    preview_url: attachment.previewUrl,
  }))
}

function mergeMetadata(current: StreamMetadata, incoming: Record<string, unknown>): StreamMetadata {
  const knowledgeSources = Array.isArray(incoming.knowledge_sources)
    ? (incoming.knowledge_sources as KnowledgeSource[])
    : current.knowledgeSources

  const retrievalInfo =
    (incoming.retrieval_info as RetrievalInfo | undefined) ?? current.retrievalInfo

  const memoryContext =
    (incoming.memory_context as StreamMetadata['memoryContext'] | undefined) ?? current.memoryContext

  const unifiedContext =
    (incoming.unified_context as StreamMetadata['unifiedContext'] | undefined) ?? current.unifiedContext

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
  }

  return {
    ...current,
    knowledgeSources,
    retrievalInfo,
    memoryContext,
    unifiedContext,
    runMetrics: Object.values(runMetrics).some((value) => value !== undefined) ? runMetrics : undefined,
    rawResponse: incoming.raw_response ?? current.rawResponse,
  }
}

async function streamSse(
  url: string,
  body: Record<string, unknown>,
  signal: AbortSignal,
  onDelta: (delta: string) => void
): Promise<ChatRunResult> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    const detail =
      (errorData as { detail?: string }).detail ||
      (errorData as { error?: string }).error ||
      `Request failed: ${response.status}`
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('Stream is not available from server response.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let content = ''
  let metadata: StreamMetadata = {}

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const records = buffer.split('\n\n')
    buffer = records.pop() || ''

    for (const record of records) {
      const dataLines = record
        .split(/\r?\n/)
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
      if (!dataLines.length) continue

      const dataText = dataLines.join('\n')
      if (!dataText || dataText === '[DONE]') continue

      let parsed: Record<string, unknown> | null = null
      try {
        parsed = JSON.parse(dataText) as Record<string, unknown>
      } catch {
        parsed = { type: 'delta', content: dataText }
      }

      if (!parsed) continue

      if (typeof parsed.error === 'string' && parsed.error) {
        throw new Error(parsed.error)
      }

      if (parsed.type === 'metadata') {
        metadata = mergeMetadata(metadata, parsed)
        continue
      }

      if (parsed.type === 'done') {
        continue
      }

      const delta =
        typeof parsed.content === 'string'
          ? parsed.content
          : typeof parsed.delta === 'string'
            ? parsed.delta
            : ''
      if (!delta) continue

      content += delta
      onDelta(delta)
    }
  }

  return { content, metadata: Object.keys(metadata).length ? metadata : undefined }
}

export function useChatStream(config: StreamConfig = {}) {
  const isStreaming = useChatStore((state) => state.isStreaming)
  const abortRef = useRef<AbortController | null>(null)

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

  const sendMessage = useCallback(
    async (payload: ChatSendPayload): Promise<ChatRunResult | undefined> => {
      const store = useChatStore.getState()
      const prompt = payload.prompt.trim()
      if (!prompt) return undefined

      let sessionId = store.currentSessionId
      if (!sessionId) {
        const session = await store.createSession()
        sessionId = session.id
      }

      const userMessageId = store.addMessage({
        role: 'user',
        content: prompt,
        attachments: payload.attachments?.length ? payload.attachments : undefined,
      })
      const assistantMessageId = store.addMessage({
        role: 'assistant',
        content: '',
        isLoading: true,
      })

      const currentState = useChatStore.getState()
      const messages = currentState.messages.map((message) => ({
        role: message.role,
        content: message.content,
      }))
      const attachments = payload.attachments ?? currentState.attachments

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
          collection_id: payload.knowledgeOverride?.collectionId ?? currentState.settings.knowledgeCollection,
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
      }

      const controller = new AbortController()
      abortRef.current = controller

      store.setError(null)
      store.setIsLoading(true)
      store.startStreaming(assistantMessageId)
      store.setStreamState({ status: 'connecting', content: '' })
      config.onStatusChange?.('connecting')

      let fullContent = ''

      try {
        const result = await streamSse(
          `${API_BASE_URL}/inference/chat/stream`,
          requestBody,
          controller.signal,
          (delta) => {
            fullContent += delta
            const activeStore = useChatStore.getState()
            activeStore.setStreamState({ status: 'streaming' })
            activeStore.updateStreamingContent(fullContent)
            config.onStatusChange?.('streaming')
            config.onChunk?.(delta, fullContent)
          }
        )

        const assistantMetadata = {
          knowledge_sources: result.metadata?.knowledgeSources,
          retrieval_info: result.metadata?.retrievalInfo,
          memory_context: result.metadata?.memoryContext,
          unified_context: result.metadata?.unifiedContext,
          raw_response: result.metadata?.rawResponse,
          run_metrics: result.metadata?.runMetrics,
        }

        const successStore = useChatStore.getState()
        successStore.updateMessage(assistantMessageId, {
          content: result.content,
          isLoading: false,
          ...assistantMetadata,
        })
        successStore.completeStreaming()
        successStore.setIsLoading(false)
        successStore.clearAttachments()
        successStore.setStreamState({ status: 'completed' })
        config.onStatusChange?.('completed')
        config.onComplete?.(result.content, result.metadata)

        if (sessionId) {
          await persistChatRunToSession(sessionId, prompt, result.content, {
            userMetadata: {
              message_id: userMessageId,
            },
            assistantMetadata,
          }).catch(() => undefined)
        }

        return result
      } catch (error) {
        const failedStore = useChatStore.getState()
        const aborted = controller.signal.aborted
        const errorMessage = aborted ? '已停止生成。' : error instanceof Error ? error.message : '请求失败'

        failedStore.updateMessage(assistantMessageId, {
          content: fullContent || errorMessage,
          isLoading: false,
        })
        if (aborted) {
          failedStore.stopStreaming()
          failedStore.setStreamState({ status: 'stopped' })
          config.onStatusChange?.('stopped')
        } else {
          failedStore.stopStreaming()
          failedStore.setStreamState({ status: 'error', error: errorMessage })
          failedStore.setError(errorMessage)
          config.onStatusChange?.('error')
          config.onError?.(errorMessage)
        }
        failedStore.setIsLoading(false)
        return undefined
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null
        }
      }
    },
    [config]
  )

  const sendCloudMessage = useCallback(
    async (payload: ChatSendPayload, cloudConfig: CloudConfig): Promise<ChatRunResult | undefined> => {
      const store = useChatStore.getState()
      const prompt = payload.prompt.trim()
      if (!prompt) return undefined

      let sessionId = store.currentSessionId
      if (!sessionId) {
        const session = await store.createSession()
        sessionId = session.id
      }

      const userMessageId = store.addMessage({
        role: 'user',
        content: prompt,
        attachments: payload.attachments?.length ? payload.attachments : undefined,
      })
      const assistantMessageId = store.addMessage({
        role: 'assistant',
        content: '',
        isLoading: true,
      })

      const currentState = useChatStore.getState()
      const messages = currentState.messages.map((message) => ({
        role: message.role,
        content: message.content,
      }))
      const attachments = payload.attachments ?? currentState.attachments

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
          collection_id: payload.knowledgeOverride?.collectionId ?? currentState.settings.knowledgeCollection,
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
      }

      const controller = new AbortController()
      abortRef.current = controller

      store.setError(null)
      store.setIsLoading(true)
      store.startStreaming(assistantMessageId)
      store.setStreamState({ status: 'connecting', content: '' })
      config.onStatusChange?.('connecting')

      let fullContent = ''

      try {
        const result = await streamSse(
          `${API_BASE_URL}/cloud/chat/stream`,
          requestBody,
          controller.signal,
          (delta) => {
            fullContent += delta
            const activeStore = useChatStore.getState()
            activeStore.setStreamState({ status: 'streaming' })
            activeStore.updateStreamingContent(fullContent)
            config.onStatusChange?.('streaming')
            config.onChunk?.(delta, fullContent)
          }
        )

        const assistantMetadata = {
          knowledge_sources: result.metadata?.knowledgeSources,
          retrieval_info: result.metadata?.retrievalInfo,
          memory_context: result.metadata?.memoryContext,
          unified_context: result.metadata?.unifiedContext,
          raw_response: result.metadata?.rawResponse,
          run_metrics: result.metadata?.runMetrics,
        }

        const successStore = useChatStore.getState()
        successStore.updateMessage(assistantMessageId, {
          content: result.content,
          isLoading: false,
          ...assistantMetadata,
        })
        successStore.completeStreaming()
        successStore.setIsLoading(false)
        successStore.clearAttachments()
        successStore.setStreamState({ status: 'completed' })
        config.onStatusChange?.('completed')
        config.onComplete?.(result.content, result.metadata)

        if (sessionId) {
          await persistChatRunToSession(sessionId, prompt, result.content, {
            userMetadata: {
              message_id: userMessageId,
            },
            assistantMetadata,
          }).catch(() => undefined)
        }

        return result
      } catch (error) {
        const failedStore = useChatStore.getState()
        const aborted = controller.signal.aborted
        const errorMessage = aborted ? '已停止生成。' : error instanceof Error ? error.message : '请求失败'

        failedStore.updateMessage(assistantMessageId, {
          content: fullContent || errorMessage,
          isLoading: false,
        })
        if (aborted) {
          failedStore.stopStreaming()
          failedStore.setStreamState({ status: 'stopped' })
          config.onStatusChange?.('stopped')
        } else {
          failedStore.stopStreaming()
          failedStore.setStreamState({ status: 'error', error: errorMessage })
          failedStore.setError(errorMessage)
          config.onStatusChange?.('error')
          config.onError?.(errorMessage)
        }
        failedStore.setIsLoading(false)
        return undefined
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null
        }
      }
    },
    [config]
  )

  return {
    sendMessage,
    sendCloudMessage,
    stop,
    isStreaming,
  }
}
