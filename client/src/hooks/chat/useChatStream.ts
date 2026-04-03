import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../../services/api'
import { useChatStore } from '../../store/chatStore'
import type {
  KnowledgeSource,
  PlaygroundAttachment,
  PlaygroundRunMetrics,
  RetrievalInfo,
} from '../../types'

interface StreamConfig {
  maxRetries?: number
  retryDelay?: number
  timeout?: number
  onChunk?: (chunk: string, fullContent: string) => void
  onComplete?: (content: string, metadata?: StreamMetadata) => void
  onError?: (error: string) => void
  onStatusChange?: (status: StreamState['status']) => void
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

interface ChatRunResult {
  content: string
  metadata?: StreamMetadata
}

interface StreamState {
  status: 'idle' | 'connecting' | 'streaming' | 'completed' | 'error' | 'stopped'
  content: string
  error: string | null
  chunksReceived: number
  startTime: number | null
  bytesReceived: number
  speed: number
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

export function useChatStream(config: StreamConfig = {}) {
  const {
    maxRetries = 3,
    retryDelay = 1000,
    timeout = 120000,
    onChunk,
    onComplete,
    onError,
    onStatusChange,
  } = config

  const [state, setState] = useState<StreamState>({
    status: 'idle',
    content: '',
    error: null,
    chunksReceived: 0,
    startTime: null,
    bytesReceived: 0,
    speed: 0,
  })

  const abortControllerRef = useRef<AbortController | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCountRef = useRef(0)
  const lastContentRef = useRef('')

  const {
    addMessage,
    startStreaming,
    updateStreamingContent,
    stopStreaming,
    completeStreaming,
    settings,
    currentSessionId,
    updateMessage,
  } = useChatStore()

  const clearTimeouts = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }, [])

  const startTimeout = useCallback(() => {
    clearTimeouts()
    timeoutRef.current = setTimeout(() => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: 'Request timed out.',
        }))
        onStatusChange?.('error')
        onError?.('Request timed out.')
      }
    }, timeout)
  }, [clearTimeouts, onError, onStatusChange, timeout])

  const finalizeRun = useCallback(
    (
      assistantMessageId: string,
      fullContent: string,
      metadata?: StreamMetadata,
      prompt?: string,
      attachments?: PlaygroundAttachment[]
    ) => {
      setState((prev) => {
        const elapsed = Date.now() - (prev.startTime || Date.now())
        return {
          ...prev,
          status: 'completed',
          content: fullContent,
          speed: elapsed > 0 ? (fullContent.length / elapsed) * 1000 : 0,
        }
      })
      onStatusChange?.('completed')

      updateStreamingContent(fullContent)
      updateMessage(assistantMessageId, {
        knowledge_sources: metadata?.knowledgeSources,
        retrieval_info: metadata?.retrievalInfo,
        memory_context: metadata?.memoryContext,
        unified_context: metadata?.unifiedContext,
        raw_response: metadata?.rawResponse,
        run_metrics: metadata?.runMetrics,
        experiment_config: prompt
          ? {
              prompt,
              systemPrompt: settings.systemPrompt,
              responseFormat: settings.responseFormat,
              modelId: settings.modelId,
              backend: settings.backend,
              temperature: settings.temperature,
              topP: settings.topP,
              maxTokens: settings.maxTokens,
              useKnowledge: settings.useKnowledge,
              knowledgeCollection: settings.knowledgeCollection,
              useMemory: settings.useMemory,
              autoRetrieve: settings.autoRetrieve,
              attachments: attachments || [],
            }
          : undefined,
      })
      completeStreaming()
      onComplete?.(fullContent, metadata)
      retryCountRef.current = 0
    },
    [
      completeStreaming,
      onComplete,
      onStatusChange,
      settings,
      updateMessage,
      updateStreamingContent,
    ]
  )

  const sendMessage = useCallback(
    async (payload: ChatSendPayload): Promise<ChatRunResult | undefined> => {
      const prompt = payload.prompt.trim()
      if (!prompt) return undefined

      const attachments = payload.attachments || []

      addMessage({
        role: 'user',
        content: prompt,
        attachments,
      })

      const assistantMessageId = addMessage({
        role: 'assistant',
        content: '',
        isLoading: true,
      })

      startStreaming(assistantMessageId)
      lastContentRef.current = ''

      setState({
        status: 'connecting',
        content: '',
        error: null,
        chunksReceived: 0,
        startTime: Date.now(),
        bytesReceived: 0,
        speed: 0,
      })
      onStatusChange?.('connecting')

      abortControllerRef.current = new AbortController()
      startTimeout()

      try {
        const useKnowledge = payload.knowledgeOverride?.enabled ?? settings.useKnowledge
        const knowledgeCollection =
          payload.knowledgeOverride?.collectionId ?? settings.knowledgeCollection
        const useMemory = payload.memoryOverride?.enabled ?? settings.useMemory

        const response = await fetch(`${API_BASE_URL}/inference/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: payload.parameterOverrides?.modelId || settings.modelId,
            messages: [{ role: 'user', content: prompt }],
            options: {
              max_tokens: payload.parameterOverrides?.maxTokens ?? settings.maxTokens,
              temperature: payload.parameterOverrides?.temperature ?? settings.temperature,
              top_p: payload.parameterOverrides?.topP ?? settings.topP,
              backend:
                payload.parameterOverrides?.backend === 'cloud'
                  ? 'ollama'
                  : payload.parameterOverrides?.backend ?? settings.backend,
            },
            system_prompt: payload.systemPrompt ?? settings.systemPrompt,
            attachments: toRequestAttachments(attachments),
            response_format: payload.responseFormat ?? settings.responseFormat,
            memory: {
              enabled: useMemory,
              auto_extract: true,
              auto_retrieve: true,
              top_k: 3,
            },
            knowledge: {
              use_knowledge: useKnowledge && !!knowledgeCollection,
              collection_id: knowledgeCollection,
              auto_retrieve: settings.autoRetrieve,
              top_k: 5,
              include_sources: true,
            },
            session: {
              session_id: currentSessionId,
              user_id: 'default',
            },
          }),
          signal: abortControllerRef.current.signal,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || `HTTP error: ${response.status}`)
        }

        const data = await response.json()
        const fullContent = data.message?.content || data.text || ''
        const metadata: StreamMetadata = {
          knowledgeSources: data.knowledge_sources,
          retrievalInfo: data.retrieval_info,
          memoryContext: data.memory_context,
          unifiedContext: data.unified_context,
          rawResponse: data.raw_response ?? data,
          runMetrics: {
            model: data.model,
            backend: data.backend,
            duration_ms:
              typeof data.duration_ms === 'number'
                ? data.duration_ms
                : typeof data.total_duration === 'number'
                  ? Math.round(data.total_duration * 1000)
                  : undefined,
            prompt_tokens: data.usage?.prompt_tokens,
            completion_tokens: data.usage?.completion_tokens,
            total_tokens: data.usage?.total_tokens,
            used_knowledge: Boolean(data.knowledge_sources?.length),
            used_memory: Boolean(data.memory_context?.retrieved),
          },
        }

        finalizeRun(assistantMessageId, fullContent, metadata, prompt, attachments)

        if (currentSessionId) {
          await fetch(`${API_BASE_URL}/chat/sessions/${currentSessionId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              messages: [
                { role: 'user', content: prompt },
                { role: 'assistant', content: fullContent },
              ],
            }),
          }).catch(console.error)
        }

        return { content: fullContent, metadata }
      } catch (error: unknown) {
        if (error instanceof Error && error.name === 'AbortError') {
          setState((prev) => ({
            ...prev,
            status: 'stopped',
          }))
          onStatusChange?.('stopped')
          stopStreaming()
          updateMessage(assistantMessageId, {
            content: `${lastContentRef.current}\n\n(Generation stopped.)`,
            isLoading: false,
          })
          return undefined
        }

        const errorMsg = error instanceof Error ? error.message : 'Request failed.'

        if (retryCountRef.current < maxRetries) {
          retryCountRef.current += 1
          setState((prev) => ({
            ...prev,
            status: 'connecting',
            error: `Retrying (${retryCountRef.current}/${maxRetries})...`,
          }))

          await new Promise((resolve) =>
            setTimeout(resolve, retryDelay * retryCountRef.current)
          )
          return sendMessage(payload)
        }

        setState((prev) => ({
          ...prev,
          status: 'error',
          error: errorMsg,
        }))
        onStatusChange?.('error')
        onError?.(errorMsg)

        updateMessage(assistantMessageId, {
          content: `Error: ${errorMsg}`,
          isLoading: false,
        })
        completeStreaming()
        return undefined
      } finally {
        clearTimeouts()
        abortControllerRef.current = null
      }
    },
    [
      addMessage,
      clearTimeouts,
      completeStreaming,
      currentSessionId,
      finalizeRun,
      maxRetries,
      onError,
      onStatusChange,
      retryDelay,
      settings,
      startStreaming,
      startTimeout,
      stopStreaming,
      updateMessage,
    ]
  )

  const sendCloudMessage = useCallback(
    async (
      payload: ChatSendPayload,
      cloudConfig: CloudConfig
    ): Promise<ChatRunResult | undefined> => {
      const prompt = payload.prompt.trim()
      if (!prompt) return undefined

      const attachments = payload.attachments || []

      addMessage({
        role: 'user',
        content: prompt,
        attachments,
      })

      const assistantMessageId = addMessage({
        role: 'assistant',
        content: '',
        isLoading: true,
      })

      startStreaming(assistantMessageId)
      lastContentRef.current = ''

      setState({
        status: 'connecting',
        content: '',
        error: null,
        chunksReceived: 0,
        startTime: Date.now(),
        bytesReceived: 0,
        speed: 0,
      })
      onStatusChange?.('connecting')

      abortControllerRef.current = new AbortController()
      startTimeout()

      try {
        const response = await fetch(`${API_BASE_URL}/cloud/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider: cloudConfig.provider,
            api_key: cloudConfig.apiKey,
            key_id: cloudConfig.keyId,
            group_id: cloudConfig.groupId,
            base_url: cloudConfig.baseUrl,
            model: cloudConfig.model,
            messages: [{ role: 'user', content: prompt }],
            stream: true,
            system_prompt: payload.systemPrompt ?? settings.systemPrompt,
            attachments: toRequestAttachments(attachments),
            response_format: payload.responseFormat ?? settings.responseFormat,
            temperature: payload.parameterOverrides?.temperature ?? settings.temperature,
            max_tokens: payload.parameterOverrides?.maxTokens ?? settings.maxTokens,
            extra_params: {
              top_p: payload.parameterOverrides?.topP ?? settings.topP,
            },
            memory: {
              enabled: payload.memoryOverride?.enabled ?? settings.useMemory,
              auto_extract: true,
              auto_retrieve: true,
              top_k: 3,
            },
            knowledge: {
              use_knowledge:
                (payload.knowledgeOverride?.enabled ?? settings.useKnowledge) &&
                !!(payload.knowledgeOverride?.collectionId ?? settings.knowledgeCollection),
              collection_id:
                payload.knowledgeOverride?.collectionId ?? settings.knowledgeCollection,
              auto_retrieve: settings.autoRetrieve,
              top_k: 5,
              include_sources: true,
            },
            session: {
              session_id: currentSessionId,
              user_id: 'default',
            },
          }),
          signal: abortControllerRef.current.signal,
        })

        if (!response.ok) {
          const error = await response.json().catch(() => ({}))
          throw new Error(error.detail || 'Cloud chat failed.')
        }

        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('Unable to read the response stream.')
        }

        const decoder = new TextDecoder()
        let fullContent = ''
        let metadata: StreamMetadata | undefined

        setState((prev) => ({
          ...prev,
          status: 'streaming',
        }))
        onStatusChange?.('streaming')

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue

            const raw = line.slice(6)
            if (raw === '[DONE]') continue

            try {
              const parsed = JSON.parse(raw)

              if (parsed.error) {
                throw new Error(parsed.error)
              }

              if (parsed.type === 'metadata') {
                metadata = {
                  ...metadata,
                  knowledgeSources: parsed.knowledge_sources ?? metadata?.knowledgeSources,
                  retrievalInfo: parsed.retrieval_info ?? metadata?.retrievalInfo,
                  memoryContext: parsed.memory_context ?? metadata?.memoryContext,
                  unifiedContext: parsed.unified_context ?? metadata?.unifiedContext,
                  rawResponse: parsed.raw_response ?? metadata?.rawResponse,
                  runMetrics: {
                    ...(metadata?.runMetrics || {}),
                    model: parsed.model || metadata?.runMetrics?.model || cloudConfig.model,
                    backend: parsed.backend || metadata?.runMetrics?.backend || 'cloud',
                    duration_ms: parsed.duration_ms ?? metadata?.runMetrics?.duration_ms,
                    prompt_tokens: parsed.usage?.prompt_tokens ?? metadata?.runMetrics?.prompt_tokens,
                    completion_tokens:
                      parsed.usage?.completion_tokens ?? metadata?.runMetrics?.completion_tokens,
                    total_tokens: parsed.usage?.total_tokens ?? metadata?.runMetrics?.total_tokens,
                    used_knowledge:
                      Boolean(parsed.knowledge_sources?.length) || metadata?.runMetrics?.used_knowledge,
                    used_memory:
                      Boolean(parsed.memory_context?.retrieved) || metadata?.runMetrics?.used_memory,
                  },
                }
                continue
              }

              if (parsed.content) {
                fullContent += parsed.content
                lastContentRef.current = fullContent
                updateStreamingContent(fullContent)

                setState((prev) => ({
                  ...prev,
                  content: fullContent,
                  chunksReceived: prev.chunksReceived + 1,
                  bytesReceived: prev.bytesReceived + parsed.content.length,
                }))

                onChunk?.(parsed.content, fullContent)
              }
            } catch (parseError) {
              if (parseError instanceof SyntaxError) {
                continue
              }
              throw parseError
            }
          }
        }

        if (!metadata) {
          metadata = {
            runMetrics: {
              model: cloudConfig.model,
              backend: 'cloud',
            },
          }
        }

        finalizeRun(assistantMessageId, fullContent, metadata, prompt, attachments)

        if (currentSessionId) {
          await fetch(`${API_BASE_URL}/chat/sessions/${currentSessionId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              messages: [
                { role: 'user', content: prompt },
                { role: 'assistant', content: fullContent },
              ],
            }),
          }).catch(console.error)
        }

        return { content: fullContent, metadata }
      } catch (error: unknown) {
        if (error instanceof Error && error.name === 'AbortError') {
          setState((prev) => ({
            ...prev,
            status: 'stopped',
          }))
          onStatusChange?.('stopped')
          stopStreaming()
          updateMessage(assistantMessageId, {
            content: `${lastContentRef.current}\n\n(Generation stopped.)`,
            isLoading: false,
          })
          return undefined
        }

        const errorMsg = error instanceof Error ? error.message : 'Cloud chat failed.'

        setState((prev) => ({
          ...prev,
          status: 'error',
          error: errorMsg,
        }))
        onStatusChange?.('error')
        onError?.(errorMsg)

        updateMessage(assistantMessageId, {
          content: `Error: ${errorMsg}`,
          isLoading: false,
        })
        completeStreaming()
        return undefined
      } finally {
        clearTimeouts()
        abortControllerRef.current = null
      }
    },
    [
      addMessage,
      clearTimeouts,
      completeStreaming,
      currentSessionId,
      finalizeRun,
      onChunk,
      onError,
      onStatusChange,
      settings,
      startStreaming,
      startTimeout,
      stopStreaming,
      updateMessage,
      updateStreamingContent,
    ]
  )

  const stop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    clearTimeouts()
    stopStreaming()
    setState((prev) => ({
      ...prev,
      status: 'stopped',
    }))
    onStatusChange?.('stopped')
  }, [clearTimeouts, onStatusChange, stopStreaming])

  const retry = useCallback(() => {
    retryCountRef.current = 0
  }, [])

  useEffect(() => {
    return () => {
      clearTimeouts()
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [clearTimeouts])

  return {
    state,
    sendMessage,
    sendCloudMessage,
    stop,
    retry,
    isStreaming: state.status === 'connecting' || state.status === 'streaming',
    isIdle: state.status === 'idle',
    isCompleted: state.status === 'completed',
    isError: state.status === 'error',
    isStopped: state.status === 'stopped',
  }
}
