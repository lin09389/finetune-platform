import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../../services/api'
import { useChatStore } from '../../store/chatStore'
import type {
  KnowledgeSource,
  PlaygroundAttachment,
  PlaygroundCandidate,
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

export interface ChatRunResult {
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

interface RunTransportOptions {
  runId?: string
  onChunk?: (content: string, fullContent: string) => void
  onStatusChange?: (status: StreamState['status']) => void
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

function toCandidate(
  candidateId: string,
  index: number,
  result?: ChatRunResult,
  error?: string
): PlaygroundCandidate {
  return {
    id: candidateId,
    index,
    content: result?.content || '',
    status: error ? 'error' : 'completed',
    error,
    raw_response: result?.metadata?.rawResponse,
    knowledge_sources: result?.metadata?.knowledgeSources,
    retrieval_info: result?.metadata?.retrievalInfo,
    memory_context: result?.metadata?.memoryContext,
    unified_context: result?.metadata?.unifiedContext,
    run_metrics: result?.metadata?.runMetrics,
  }
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

  const abortControllersRef = useRef<Map<string, AbortController>>(new Map())
  const timeoutRefs = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const retryCountsRef = useRef<Map<string, number>>(new Map())
  const lastContentRef = useRef<Map<string, string>>(new Map())

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

  const clearTimeoutFor = useCallback((runId: string) => {
    const timeoutHandle = timeoutRefs.current.get(runId)
    if (timeoutHandle) {
      clearTimeout(timeoutHandle)
      timeoutRefs.current.delete(runId)
    }
  }, [])

  const clearAllTimeouts = useCallback(() => {
    for (const timeoutHandle of timeoutRefs.current.values()) {
      clearTimeout(timeoutHandle)
    }
    timeoutRefs.current.clear()
  }, [])

  const startTimeout = useCallback(
    (runId: string) => {
      clearTimeoutFor(runId)
      const timeoutHandle = setTimeout(() => {
        const controller = abortControllersRef.current.get(runId)
        if (!controller) {
          return
        }
        controller.abort()
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: 'Request timed out.',
        }))
        onStatusChange?.('error')
        onError?.('Request timed out.')
      }, timeout)
      timeoutRefs.current.set(runId, timeoutHandle)
    },
    [clearTimeoutFor, onError, onStatusChange, timeout]
  )

  const buildExperimentConfig = useCallback(
    (prompt: string, attachments: PlaygroundAttachment[] = []) => ({
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
      candidateCount: settings.candidateCount,
      attachments,
    }),
    [settings]
  )

  const saveSessionMessages = useCallback(
    async (prompt: string, content: string) => {
      if (!currentSessionId) {
        return
      }

      await fetch(`${API_BASE_URL}/chat/sessions/${currentSessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [
            { role: 'user', content: prompt },
            { role: 'assistant', content },
          ],
        }),
      }).catch(console.error)
    },
    [currentSessionId]
  )

  const finalizeSingleRun = useCallback(
    (
      runId: string,
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
        experiment_config: prompt ? buildExperimentConfig(prompt, attachments || []) : undefined,
      })
      completeStreaming()
      onComplete?.(fullContent, metadata)
      retryCountsRef.current.set(runId, 0)
    },
    [
      buildExperimentConfig,
      completeStreaming,
      onComplete,
      onStatusChange,
      updateMessage,
      updateStreamingContent,
    ]
  )

  const runLocalTransport = useCallback(
    async (
      payload: ChatSendPayload,
      options: RunTransportOptions = {}
    ): Promise<ChatRunResult | undefined> => {
      const prompt = payload.prompt.trim()
      if (!prompt) {
        return undefined
      }

      const runId = options.runId || `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
      const attachments = payload.attachments || []
      const retryCount = retryCountsRef.current.get(runId) || 0

      abortControllersRef.current.set(runId, new AbortController())
      startTimeout(runId)
      options.onStatusChange?.('connecting')

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
          signal: abortControllersRef.current.get(runId)?.signal,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || `HTTP error: ${response.status}`)
        }

        options.onStatusChange?.('streaming')

        const data = await response.json()
        const fullContent = data.message?.content || data.text || ''
        lastContentRef.current.set(runId, fullContent)
        options.onChunk?.(fullContent, fullContent)
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

        return { content: fullContent, metadata }
      } catch (error: unknown) {
        if (error instanceof Error && error.name === 'AbortError') {
          options.onStatusChange?.('stopped')
          return undefined
        }

        const errorMessage = error instanceof Error ? error.message : 'Request failed.'
        if (retryCount < maxRetries) {
          retryCountsRef.current.set(runId, retryCount + 1)
          await new Promise((resolve) => setTimeout(resolve, retryDelay * (retryCount + 1)))
          return runLocalTransport(payload, options)
        }
        options.onStatusChange?.('error')
        throw new Error(errorMessage)
      } finally {
        clearTimeoutFor(runId)
        abortControllersRef.current.delete(runId)
      }
    },
    [
      clearTimeoutFor,
      currentSessionId,
      maxRetries,
      retryDelay,
      settings,
      startTimeout,
    ]
  )

  const runCloudTransport = useCallback(
    async (
      payload: ChatSendPayload,
      cloudConfig: CloudConfig,
      options: RunTransportOptions = {}
    ): Promise<ChatRunResult | undefined> => {
      const prompt = payload.prompt.trim()
      if (!prompt) {
        return undefined
      }

      const runId = options.runId || `cloud_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
      const attachments = payload.attachments || []

      abortControllersRef.current.set(runId, new AbortController())
      startTimeout(runId)
      options.onStatusChange?.('connecting')

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
          signal: abortControllersRef.current.get(runId)?.signal,
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

        options.onStatusChange?.('streaming')

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read()
          if (done) {
            break
          }

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')
          for (const line of lines) {
            if (!line.startsWith('data: ')) {
              continue
            }

            const raw = line.slice(6)
            if (raw === '[DONE]') {
              continue
            }

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
                lastContentRef.current.set(runId, fullContent)
                options.onChunk?.(parsed.content, fullContent)
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

        return { content: fullContent, metadata }
      } catch (error: unknown) {
        if (error instanceof Error && error.name === 'AbortError') {
          options.onStatusChange?.('stopped')
          return undefined
        }

        options.onStatusChange?.('error')
        throw error instanceof Error ? error : new Error('Cloud chat failed.')
      } finally {
        clearTimeoutFor(runId)
        abortControllersRef.current.delete(runId)
      }
    },
    [clearTimeoutFor, currentSessionId, settings, startTimeout]
  )

  const sendMessage = useCallback(
    async (payload: ChatSendPayload): Promise<ChatRunResult | undefined> => {
      const prompt = payload.prompt.trim()
      if (!prompt) {
        return undefined
      }

      const runId = `single_local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
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
      lastContentRef.current.set(runId, '')
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

      try {
        const result = await runLocalTransport(payload, {
          runId,
          onChunk: (chunk, fullContent) => {
            updateStreamingContent(fullContent)
            setState((prev) => ({
              ...prev,
              status: 'streaming',
              content: fullContent,
              chunksReceived: prev.chunksReceived + 1,
              bytesReceived: prev.bytesReceived + chunk.length,
            }))
            onChunk?.(chunk, fullContent)
          },
          onStatusChange,
        })

        if (!result) {
          setState((prev) => ({
            ...prev,
            status: 'stopped',
          }))
          stopStreaming()
          updateMessage(assistantMessageId, {
            content: `${lastContentRef.current.get(runId) || ''}\n\n(Generation stopped.)`,
            isLoading: false,
          })
          return undefined
        }

        finalizeSingleRun(runId, assistantMessageId, result.content, result.metadata, prompt, attachments)
        await saveSessionMessages(prompt, result.content)
        return result
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : 'Request failed.'
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: errorMessage,
        }))
        onStatusChange?.('error')
        onError?.(errorMessage)
        updateMessage(assistantMessageId, {
          content: `Error: ${errorMessage}`,
          isLoading: false,
        })
        completeStreaming()
        return undefined
      }
    },
    [
      addMessage,
      completeStreaming,
      finalizeSingleRun,
      onChunk,
      onError,
      onStatusChange,
      runLocalTransport,
      saveSessionMessages,
      startStreaming,
      stopStreaming,
      updateMessage,
      updateStreamingContent,
    ]
  )

  const sendCloudMessage = useCallback(
    async (
      payload: ChatSendPayload,
      cloudConfig: CloudConfig
    ): Promise<ChatRunResult | undefined> => {
      const prompt = payload.prompt.trim()
      if (!prompt) {
        return undefined
      }

      const runId = `single_cloud_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
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
      lastContentRef.current.set(runId, '')
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

      try {
        const result = await runCloudTransport(payload, cloudConfig, {
          runId,
          onChunk: (chunk, fullContent) => {
            updateStreamingContent(fullContent)
            setState((prev) => ({
              ...prev,
              status: 'streaming',
              content: fullContent,
              chunksReceived: prev.chunksReceived + 1,
              bytesReceived: prev.bytesReceived + chunk.length,
            }))
            onChunk?.(chunk, fullContent)
          },
          onStatusChange,
        })

        if (!result) {
          setState((prev) => ({
            ...prev,
            status: 'stopped',
          }))
          stopStreaming()
          updateMessage(assistantMessageId, {
            content: `${lastContentRef.current.get(runId) || ''}\n\n(Generation stopped.)`,
            isLoading: false,
          })
          return undefined
        }

        finalizeSingleRun(runId, assistantMessageId, result.content, result.metadata, prompt, attachments)
        await saveSessionMessages(prompt, result.content)
        return result
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : 'Cloud chat failed.'
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: errorMessage,
        }))
        onStatusChange?.('error')
        onError?.(errorMessage)
        updateMessage(assistantMessageId, {
          content: `Error: ${errorMessage}`,
          isLoading: false,
        })
        completeStreaming()
        return undefined
      }
    },
    [
      addMessage,
      completeStreaming,
      finalizeSingleRun,
      onChunk,
      onError,
      onStatusChange,
      runCloudTransport,
      saveSessionMessages,
      startStreaming,
      stopStreaming,
      updateMessage,
      updateStreamingContent,
    ]
  )

  const runExperimentCandidates = useCallback(
    async (
      payload: ChatSendPayload,
      count: number,
      cloudConfig?: CloudConfig
    ): Promise<PlaygroundCandidate[]> => {
      const safeCount = Math.min(4, Math.max(1, count))
      const prompt = payload.prompt.trim()
      if (!prompt) {
        return []
      }

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

      const candidates = await Promise.all(
        Array.from({ length: safeCount }, async (_, index) => {
          const candidateId = `candidate_${Date.now()}_${index + 1}_${Math.random().toString(36).slice(2, 8)}`
          try {
            const result =
              cloudConfig && (payload.parameterOverrides?.backend === 'cloud' || settings.backend === 'cloud')
                ? await runCloudTransport(payload, cloudConfig, {
                    runId: candidateId,
                    onChunk: (_chunk, fullContent) => {
                      if (index === 0) {
                        setState((prev) => ({
                          ...prev,
                          status: 'streaming',
                          content: fullContent,
                        }))
                      }
                    },
                    onStatusChange: (status) => {
                      if (index === 0) {
                        setState((prev) => ({
                          ...prev,
                          status,
                        }))
                      }
                    },
                  })
                : await runLocalTransport(payload, {
                    runId: candidateId,
                    onChunk: (_chunk, fullContent) => {
                      if (index === 0) {
                        setState((prev) => ({
                          ...prev,
                          status: 'streaming',
                          content: fullContent,
                        }))
                      }
                    },
                    onStatusChange: (status) => {
                      if (index === 0) {
                        setState((prev) => ({
                          ...prev,
                          status,
                        }))
                      }
                    },
                  })

            if (!result) {
              return {
                id: candidateId,
                index,
                content: lastContentRef.current.get(candidateId) || '',
                status: 'stopped' as const,
              }
            }

            return toCandidate(candidateId, index, result)
          } catch (error: unknown) {
            const messageText = error instanceof Error ? error.message : 'Request failed.'
            return toCandidate(candidateId, index, undefined, messageText)
          }
        })
      )

      const primary = candidates.find((candidate) => candidate.status === 'completed') || candidates[0]
      if (primary) {
        setState((prev) => ({
          ...prev,
          status: candidates.some((candidate) => candidate.status === 'completed') ? 'completed' : 'error',
          content: primary.content,
        }))
      }

      return candidates
    },
    [onStatusChange, runCloudTransport, runLocalTransport, settings.backend]
  )

  const stop = useCallback(() => {
    for (const controller of abortControllersRef.current.values()) {
      controller.abort()
    }
    abortControllersRef.current.clear()
    clearAllTimeouts()
    stopStreaming()
    setState((prev) => ({
      ...prev,
      status: 'stopped',
    }))
    onStatusChange?.('stopped')
  }, [clearAllTimeouts, onStatusChange, stopStreaming])

  const retry = useCallback(() => {
    retryCountsRef.current.clear()
  }, [])

  useEffect(() => {
    return () => {
      clearAllTimeouts()
      for (const controller of abortControllersRef.current.values()) {
        controller.abort()
      }
      abortControllersRef.current.clear()
    }
  }, [clearAllTimeouts])

  return {
    state,
    sendMessage,
    sendCloudMessage,
    runExperimentCandidates,
    stop,
    retry,
    isStreaming: state.status === 'connecting' || state.status === 'streaming',
    isIdle: state.status === 'idle',
    isCompleted: state.status === 'completed',
    isError: state.status === 'error',
    isStopped: state.status === 'stopped',
  }
}
