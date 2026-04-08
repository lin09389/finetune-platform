import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../../services/api'
import {
  executeAgentAction,
  resumeAgentFromTimelineEvent,
  resumeAgentSession,
  runAgentLoop,
} from '../../services/agentRunApi'
import { persistChatRunToSession } from '../../services/chatSessionApi'
import { useChatStore } from '../../store/chatStore'
import type {
  AgentPendingConfirmation,
  AgentTaskStatus,
  AgentTimelineEvent,
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
  agentContext?: Record<string, unknown>
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

interface AgentRunResult {
  status: AgentTaskStatus
  response?: ChatRunResult
  pendingConfirmation?: AgentPendingConfirmation | null
  timeline: AgentTimelineEvent[]
  summary?: string
}

interface PatchApplyResult extends AgentRunResult {}

interface PatchApplyOptions {
  rerunCommand?: string
  autoFinalize?: boolean
}

interface AgentDecisionData {
  action?: string
  confidence?: number
  description?: string
  execution?: {
    status?: string
    error?: string | null
  }
  intent_type?: string
  need_confirm?: boolean
  params?: Record<string, unknown>
  result?: Record<string, unknown> & {
    need_inference?: boolean
    message?: string
    feedback?: string
    recovery_hint?: string
    prompt_override?: string
    auto_repair_pipeline?: boolean
    rerun_command?: string
    completed_actions?: Array<{
      action?: string
      params?: Record<string, unknown>
      success?: boolean
      message?: string
      error?: string | null
      data?: Record<string, unknown>
    }>
    step_records?: Array<{
      step?: number
      status?: string
      action?: string
      params?: Record<string, unknown>
      description?: string
      result?: Record<string, unknown>
    }>
  }
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

function createAgentEvent(
  type: AgentTimelineEvent['type'],
  title: string,
  overrides: Partial<AgentTimelineEvent> = {}
): AgentTimelineEvent {
  return {
    id: `agent_event_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    type,
    title,
    createdAt: new Date().toISOString(),
    ...overrides,
  }
}

function extractPatchDraftContent(text: string) {
  const fencedMatch = text.match(/```(?:diff|patch)?\s*\n([\s\S]*?)```/i)
  const candidate = fencedMatch?.[1]?.trim() || text.trim()

  if (
    !candidate ||
    (!candidate.includes('diff --git') &&
      !(candidate.includes('--- ') && candidate.includes('+++ ')) &&
      !candidate.includes('@@'))
  ) {
    return null
  }

  return candidate
}

function buildAutomaticRepairSummary(options: {
  patchedFiles: string[]
  rerunCommand?: string
  passed?: number
  failed?: number
}) {
  const fileText = options.patchedFiles.length
    ? `Patched ${options.patchedFiles.join(', ')}.`
    : 'Applied the generated patch draft.'
  const verificationText = options.rerunCommand
    ? ` Reran \`${options.rerunCommand}\` and got ${options.passed || 0} passed / ${options.failed || 0} failed.`
    : ''
  const recommendation =
    (options.failed || 0) > 0
      ? ' Review the remaining failing output before drafting the next patch.'
      : ' Verification passed, so the task is ready for a completion summary or handoff.'
  return `${fileText}${verificationText}${recommendation}`
}

function buildAutomaticHandoffNote(options: {
  patchedFiles: string[]
  rerunCommand?: string
  passed?: number
  failed?: number
}) {
  const fileText = options.patchedFiles.length
    ? `Updated files: ${options.patchedFiles.join(', ')}.`
    : 'Updated the generated target files.'
  const verificationText = options.rerunCommand
    ? ` Verified with \`${options.rerunCommand}\` (${options.passed || 0} passed, ${options.failed || 0} failed).`
    : ''
  return `${fileText}${verificationText} Next owner step: review the final diff once and merge or continue the broader task.`
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

function buildAgentFollowupPrompt(
  followupPrompt: string,
  completedActions: Array<{
    action?: string
    success?: boolean
    data?: Record<string, unknown>
  }>
) {
  const latestFileRead = [...completedActions]
    .reverse()
    .find((step) => step.action === 'file_read' && step.success)

  if (!latestFileRead?.data) {
    return null
  }

  const filePath =
    typeof latestFileRead.data.path === 'string'
      ? latestFileRead.data.path
      : typeof latestFileRead.data.file_path === 'string'
        ? latestFileRead.data.file_path
        : 'unknown file'

  const content =
    typeof latestFileRead.data.content === 'string' && latestFileRead.data.content.trim()
      ? latestFileRead.data.content
      : typeof latestFileRead.data.content_preview === 'string'
        ? latestFileRead.data.content_preview
        : ''

  if (!content.trim()) {
    return null
  }

  return `${followupPrompt}\n\nFile: ${filePath}\n\nFile content:\n\`\`\`\n${content.slice(0, 4000)}\n\`\`\``
}

function buildVerificationOutcome(
  rerunData: {
  success?: boolean
  message?: string
  error?: string
  data?: Record<string, unknown>
},
  options?: {
    patchedFiles?: string[]
    rerunCommand?: string
  }
) {
  const testSummary =
    rerunData.data && typeof rerunData.data.test_summary === 'object' && rerunData.data.test_summary
      ? (rerunData.data.test_summary as {
          failed?: number
          passed?: number
          failure_files?: string[]
        })
      : null
  const hasFailures = Boolean((testSummary?.failed || 0) > 0 || rerunData.success === false)
  const failureFiles =
    Array.isArray(testSummary?.failure_files) && testSummary?.failure_files.length
      ? testSummary.failure_files.filter((file): file is string => typeof file === 'string')
      : []

  return {
    title: hasFailures ? 'Verification still failing' : 'Patch verified successfully',
    description: hasFailures
      ? failureFiles.length
        ? `Tests are still failing after the patch. Start with ${failureFiles[0]} before redrafting the patch.`
        : 'Tests are still failing after the patch. Inspect the failure details before redrafting the patch.'
      : 'The patched code passed the rerun command. Review the touched file once, then keep moving.',
    status: hasFailures ? ('failed' as const) : ('completed' as const),
    payload: {
      verification_outcome: hasFailures ? 'failed' : 'passed',
      failure_files: failureFiles,
      patched_files: options?.patchedFiles || [],
      rerun_command: options?.rerunCommand,
      passed: testSummary?.passed || 0,
      failed: testSummary?.failed || 0,
      summary: rerunData.message || rerunData.error,
    },
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
    agentWorkspaceRoot,
    autoApproveSafeTools,
    setAgentTaskStatus,
    appendAgentTimeline,
    replaceAgentTimeline,
    clearAgentTimeline,
    setPendingAgentConfirmation,
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

      await persistChatRunToSession(currentSessionId, prompt, content)
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

  const handleAgentDecision = useCallback(
    async (
      data: AgentDecisionData,
      payload: ChatSendPayload,
      cloudConfig?: CloudConfig
    ): Promise<AgentRunResult | undefined> => {
      const executionStatus = String(data.execution?.status || '')
      const intentType = data.intent_type || 'agent_task'
      const description = data.description || payload.prompt
      const action = data.action || intentType

      appendAgentTimeline(
        createAgentEvent('plan_update', 'Intent detected', {
          description,
          status: 'completed',
          payload: {
            intent_type: intentType,
            confidence: data.confidence,
          },
        })
      )

      if (data.need_confirm) {
        const pendingConfirmation: AgentPendingConfirmation = {
          action,
          description,
          params: data.params || {},
          riskLevel: 'high',
        }
        setPendingAgentConfirmation(pendingConfirmation)
        setAgentTaskStatus('waiting_confirmation')
        appendAgentTimeline(
          createAgentEvent('tool_call', `Awaiting confirmation for ${action}`, {
            tool_name: action,
            status: 'pending',
            payload: data.params || {},
          })
        )
        appendAgentTimeline(
          createAgentEvent('confirmation_request', 'Confirmation required', {
            description,
            status: 'pending',
            payload: {
              action,
              params: data.params || {},
            },
          })
        )
        return {
          status: 'waiting_confirmation',
          pendingConfirmation,
          timeline: [],
          summary: description,
        }
      }

      const completedActions = Array.isArray(data.result?.completed_actions)
        ? data.result?.completed_actions
        : []
      const stepRecords = Array.isArray(data.result?.step_records) ? data.result?.step_records : []

      if (stepRecords.length > 0) {
        stepRecords.forEach((stepRecord) => {
          appendAgentTimeline(
            createAgentEvent('plan_update', `Step ${stepRecord.step || '?'} status`, {
              description:
                stepRecord.description ||
                `Step ${stepRecord.step || '?'} is ${stepRecord.status || 'pending'}.`,
              status:
                stepRecord.status === 'failed'
                  ? 'failed'
                  : stepRecord.status === 'completed'
                    ? 'completed'
                    : stepRecord.status === 'waiting_confirmation'
                      ? 'pending'
                      : 'running',
              payload: stepRecord,
            })
          )
        })
      }

      if (completedActions.length > 0) {
        completedActions.forEach((step, index) => {
          appendAgentTimeline(
            createAgentEvent('tool_call', `Step ${index + 1}: ${step.action || 'action'}`, {
              tool_name: step.action,
              status: step.success ? 'completed' : 'failed',
              payload: step.params || {},
            })
          )
          appendAgentTimeline(
            createAgentEvent('tool_result', step.success ? 'Step completed' : 'Step failed', {
              tool_name: step.action,
              description: step.message || step.error || `Completed ${step.action || 'action'}.`,
              status: step.success ? 'completed' : 'failed',
              payload: step.data || {},
            })
          )

          const actionName = step.action || ''
          if (actionName === 'file_read' && step.success && typeof step.data?.content === 'string') {
            lastContentRef.current.set('latest_agent_content', step.data.content)
          }
          if (
            actionName.startsWith('file_') ||
            actionName.startsWith('dir_')
          ) {
            appendAgentTimeline(
              createAgentEvent('file_change', `File step ${index + 1}`, {
                tool_name: actionName,
                status: step.success ? 'completed' : 'failed',
                description: step.message || step.error || `Processed ${actionName}.`,
                payload: {
                  action: actionName,
                  message: step.message,
                  error: step.error,
                  ...(step.data || {}),
                },
              })
            )
          }

          if (
            actionName === 'command_execute' ||
            actionName === 'command_run' ||
            actionName === 'tests_run'
          ) {
            appendAgentTimeline(
              createAgentEvent('command_output', `Command step ${index + 1}`, {
                tool_name: actionName,
                status: step.success ? 'completed' : 'failed',
                description: step.message || step.error || `Executed ${actionName}.`,
                payload: {
                  action: actionName,
                  message: step.message,
                  error: step.error,
                  ...(step.data || {}),
                },
              })
            )
          }
        })
      }

      if (typeof data.result?.loop_summary === 'string' && data.result.loop_summary.trim()) {
        appendAgentTimeline(
          createAgentEvent('task_status', 'Loop summary', {
            description: data.result.loop_summary,
            status:
              executionStatus === 'failed'
                ? 'failed'
                : executionStatus === 'needs_confirmation'
                  ? 'pending'
                  : 'completed',
            payload: {
              loop_summary: data.result.loop_summary,
              completed_steps: data.result.completed_steps,
              failed_steps: data.result.failed_steps,
              waiting_steps: data.result.waiting_steps,
              inference_steps: data.result.inference_steps,
            },
          })
        )
      }

      if (
        typeof data.result?.recommended_next_step === 'string' &&
        data.result.recommended_next_step.trim()
      ) {
        appendAgentTimeline(
          createAgentEvent('task_status', 'Recommended next step', {
            description: data.result.recommended_next_step,
            status:
              executionStatus === 'failed'
                ? 'failed'
                : executionStatus === 'needs_confirmation'
                  ? 'pending'
                  : 'completed',
            payload: {
              recommended_next_step: data.result.recommended_next_step,
            },
          })
        )
      }

      if (data.result?.recovery_hint) {
        appendAgentTimeline(
          createAgentEvent('task_status', 'Recovery guidance', {
            description: data.result.recovery_hint,
            status: executionStatus === 'failed' ? 'failed' : 'completed',
          })
        )
      }

      const followupPrompt =
        typeof payload.agentContext?.followup_prompt === 'string'
          ? payload.agentContext.followup_prompt
          : undefined
      const promptOverride =
        (typeof data.result?.prompt_override === 'string' ? data.result.prompt_override : undefined) ||
        (followupPrompt ? buildAgentFollowupPrompt(followupPrompt, completedActions) : null)

      if (data.result?.need_inference || action === 'conversation' || executionStatus === 'planned' || promptOverride) {
        setAgentTaskStatus('running')
        appendAgentTimeline(
          createAgentEvent('assistant_message', 'Switching to model generation', {
            description: promptOverride
              ? 'The agent gathered the file context and is now summarizing the likely failure points.'
              : 'This task requires reasoning or drafting, so the assistant is generating content next.',
            status: 'running',
          })
        )
        const followupPayload: ChatSendPayload = promptOverride
          ? {
              ...payload,
              prompt: promptOverride,
              attachments: [],
              agentContext: undefined,
            }
          : payload
        const generated =
          cloudConfig && (payload.parameterOverrides?.backend === 'cloud' || settings.backend === 'cloud')
            ? await sendCloudMessage(followupPayload, cloudConfig)
            : await sendMessage(followupPayload)

        if (!generated) {
          setAgentTaskStatus('stopped')
          appendAgentTimeline(
            createAgentEvent('task_status', 'Task stopped', {
              description: 'Generation stopped before completion.',
              status: 'cancelled',
              payload: { status: 'stopped' },
            })
          )
          return {
            status: 'stopped',
            timeline: [],
          }
        }

        lastContentRef.current.set('latest_agent_content', generated.content)
        appendAgentTimeline(
          createAgentEvent('assistant_message', 'Generation completed', {
            description: generated.content.slice(0, 240) || 'The assistant completed the requested task.',
            status: 'completed',
          })
        )

        const autoRepairEnabled = Boolean(
          payload.agentContext?.auto_repair_pipeline || data.result?.auto_repair_pipeline
        )
        const generatedPatchDraft =
          promptOverride && autoRepairEnabled ? extractPatchDraftContent(generated.content) : null
        if (generatedPatchDraft) {
          const rerunCommandFromResult =
            typeof data.result?.rerun_command === 'string' ? data.result.rerun_command : undefined
          const rerunCommandFromSteps = [...completedActions]
            .reverse()
            .find(
              (step) =>
                step.action === 'tests_run' &&
                typeof step.data?.command === 'string' &&
                step.data.command.trim()
            )?.data?.command as string | undefined
          const pendingConfirmation: AgentPendingConfirmation = {
            action: 'file_patch',
            description:
              'Patch draft ready. Confirm to apply it and continue verification automatically.',
            params: {
              patch: generatedPatchDraft,
              rerun_command: rerunCommandFromResult || rerunCommandFromSteps,
              auto_finalize: true,
            },
            riskLevel: 'high',
          }
          setPendingAgentConfirmation(pendingConfirmation)
          setAgentTaskStatus('waiting_confirmation')
          appendAgentTimeline(
            createAgentEvent('confirmation_request', 'Patch draft ready for review', {
              description:
                'The agent drafted a patch and paused before applying it. Confirm to continue the automatic repair pipeline.',
              status: 'pending',
              payload: {
                action: 'file_patch',
                rerun_command: rerunCommandFromResult || rerunCommandFromSteps,
                auto_finalize: true,
              },
            })
          )
          appendAgentTimeline(
            createAgentEvent('task_status', 'Awaiting patch confirmation', {
              description:
                'The patch draft is ready. Confirm once to apply it, rerun verification, and finalize the repair automatically.',
              status: 'pending',
              payload: {
                status: 'waiting_confirmation',
                action: 'file_patch',
                rerun_command: rerunCommandFromResult || rerunCommandFromSteps,
                auto_finalize: true,
              },
            })
          )
          return {
            status: 'waiting_confirmation',
            response: generated,
            pendingConfirmation,
            timeline: [],
            summary: 'Patch draft ready for review.',
          }
        }

        setAgentTaskStatus('completed')
        appendAgentTimeline(
          createAgentEvent('task_status', 'Task completed', {
          status: 'completed',
          payload: { status: 'completed' },
        })
      )
        return {
          status: 'completed',
          response: generated,
          timeline: [],
          summary:
            (typeof data.result?.loop_summary === 'string' && data.result.loop_summary) || generated.content,
        }
      }

      setAgentTaskStatus(executionStatus === 'failed' ? 'failed' : 'completed')
      appendAgentTimeline(
        createAgentEvent('tool_call', `Run ${action}`, {
          tool_name: action,
          status: executionStatus === 'failed' ? 'failed' : 'completed',
          payload: data.params || {},
        })
      )
      appendAgentTimeline(
        createAgentEvent('tool_result', executionStatus === 'failed' ? 'Action failed' : 'Action completed', {
          tool_name: action,
          description:
            data.execution?.error || data.result?.message || data.result?.feedback || description,
          status: executionStatus === 'failed' ? 'failed' : 'completed',
          payload: data.result || data.execution || {},
        })
      )
      appendAgentTimeline(
        createAgentEvent('task_status', executionStatus === 'failed' ? 'Task failed' : 'Task completed', {
          status: executionStatus === 'failed' ? 'failed' : 'completed',
          payload: { status: executionStatus === 'failed' ? 'failed' : 'completed' },
        })
      )
      return {
        status: executionStatus === 'failed' ? 'failed' : 'completed',
        timeline: [],
        summary:
          (typeof data.result?.loop_summary === 'string' && data.result.loop_summary) ||
          data.result?.message ||
          data.execution?.error ||
          description,
      }
    },
    [
      appendAgentTimeline,
      sendCloudMessage,
      sendMessage,
      setAgentTaskStatus,
      setPendingAgentConfirmation,
      settings.backend,
    ]
  )

  const runAgentTask = useCallback(
    async (payload: ChatSendPayload, cloudConfig?: CloudConfig): Promise<AgentRunResult | undefined> => {
      const prompt = payload.prompt.trim()
      if (!prompt) {
        return undefined
      }

      addMessage({
        role: 'user',
        content: prompt,
        attachments: payload.attachments || [],
      })

      clearAgentTimeline()
      setPendingAgentConfirmation(null)
      setAgentTaskStatus('planning')

      const timeline: AgentTimelineEvent[] = [
        createAgentEvent('task_status', 'Task received', {
          description: 'Agent is analyzing the request and deciding the next step.',
          status: 'running',
          payload: { status: 'planning' },
        }),
        createAgentEvent('plan_update', 'Planning next step', {
          description: prompt,
          status: 'running',
        }),
      ]
      replaceAgentTimeline(timeline)

      try {
        const data = await runAgentLoop<AgentDecisionData>({
          message: prompt,
          auto_confirm: autoApproveSafeTools,
          session_id: currentSessionId,
          max_steps: 5,
          context: {
            workspace_root: agentWorkspaceRoot,
            content: lastContentRef.current.get('latest_agent_content') || '',
            attachments: toRequestAttachments(payload.attachments || []),
            ...(payload.agentContext || {}),
          },
        })
        return handleAgentDecision(data, payload, cloudConfig)
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : 'Agent task failed.'
        setPendingAgentConfirmation(null)
        setAgentTaskStatus('failed')
        appendAgentTimeline(
          createAgentEvent('task_status', 'Task failed', {
            description: errorMessage,
            status: 'failed',
            payload: { status: 'failed' },
          })
        )
        onError?.(errorMessage)
        return {
          status: 'failed',
          timeline: [],
          summary: errorMessage,
        }
      }
    },
    [
      addMessage,
      agentWorkspaceRoot,
      appendAgentTimeline,
      autoApproveSafeTools,
      clearAgentTimeline,
      currentSessionId,
      handleAgentDecision,
      onError,
      replaceAgentTimeline,
      sendCloudMessage,
      sendMessage,
      setAgentTaskStatus,
      setPendingAgentConfirmation,
      settings.backend,
    ]
  )

  const resumeAgentTask = useCallback(
    async (payload: ChatSendPayload, cloudConfig?: CloudConfig): Promise<AgentRunResult | undefined> => {
      if (!currentSessionId) {
        return runAgentTask(payload, cloudConfig)
      }

      setPendingAgentConfirmation(null)
      setAgentTaskStatus('running')
      appendAgentTimeline(
        createAgentEvent('task_status', 'Resuming task', {
          description: 'Loading the latest execution state from the current session.',
          status: 'running',
          payload: { status: 'running' },
        })
      )

      try {
        const data = await resumeAgentSession<AgentDecisionData>({
          session_id: currentSessionId,
          auto_confirm: autoApproveSafeTools,
          context: {
            workspace_root: agentWorkspaceRoot,
            attachments: toRequestAttachments(payload.attachments || []),
          },
        })
        return handleAgentDecision(
          {
            ...data,
            description: data.description || payload.prompt || 'Continue the current task.',
          },
          payload,
          cloudConfig
        )
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : 'Agent resume failed.'
        setAgentTaskStatus('failed')
        appendAgentTimeline(
          createAgentEvent('task_status', 'Resume failed', {
            description: errorMessage,
            status: 'failed',
            payload: { status: 'failed' },
          })
        )
        onError?.(errorMessage)
        return {
          status: 'failed',
          timeline: [],
          summary: errorMessage,
        }
      }
    },
    [
      agentWorkspaceRoot,
      appendAgentTimeline,
      autoApproveSafeTools,
      currentSessionId,
      handleAgentDecision,
      onError,
      runAgentTask,
      setAgentTaskStatus,
      setPendingAgentConfirmation,
    ]
  )

  const resumeAgentFromEvent = useCallback(
    async (
      eventId: string,
      payload: ChatSendPayload,
      cloudConfig?: CloudConfig
    ): Promise<AgentRunResult | undefined> => {
      if (!currentSessionId) {
        return runAgentTask(payload, cloudConfig)
      }

      setPendingAgentConfirmation(null)
      setAgentTaskStatus('running')
      appendAgentTimeline(
        createAgentEvent('task_status', 'Resuming from selected step', {
          description: 'Loading the selected execution state from the current session.',
          status: 'running',
          payload: { status: 'running', event_id: eventId },
        })
      )

      try {
        const data = await resumeAgentFromTimelineEvent<AgentDecisionData>({
          session_id: currentSessionId,
          event_id: eventId,
          auto_confirm: autoApproveSafeTools,
          context: {
            workspace_root: agentWorkspaceRoot,
            attachments: toRequestAttachments(payload.attachments || []),
          },
        })
        return handleAgentDecision(
          {
            ...data,
            description: data.description || payload.prompt || 'Continue from the selected task step.',
          },
          payload,
          cloudConfig
        )
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : 'Resume from event failed.'
        setAgentTaskStatus('failed')
        appendAgentTimeline(
          createAgentEvent('task_status', 'Resume from step failed', {
            description: errorMessage,
            status: 'failed',
            payload: { status: 'failed', event_id: eventId },
          })
        )
        onError?.(errorMessage)
        return {
          status: 'failed',
          timeline: [],
          summary: errorMessage,
        }
      }
    },
    [
      agentWorkspaceRoot,
      appendAgentTimeline,
      autoApproveSafeTools,
      currentSessionId,
      handleAgentDecision,
      onError,
      runAgentTask,
      setAgentTaskStatus,
      setPendingAgentConfirmation,
    ]
  )

  const applyPatchDraft = useCallback(
    async (patch: string, options?: PatchApplyOptions): Promise<PatchApplyResult | undefined> => {
      if (!patch.trim()) {
        return undefined
      }

      const recentFailedTestsCommand = [...useChatStore.getState().agentTimeline]
        .reverse()
        .find(
          (event) =>
            event.tool_name === 'tests_run' &&
            event.status === 'failed' &&
            typeof event.payload?.command === 'string' &&
            event.payload.command.trim()
        )?.payload?.command as string | undefined

      setAgentTaskStatus('running')
      appendAgentTimeline(
        createAgentEvent('tool_call', 'Applying patch draft', {
          tool_name: 'file_patch',
          description: 'Applying the generated patch draft to the workspace.',
          status: 'running',
          payload: { patch_preview: patch.slice(0, 400) },
        })
      )

      try {
        const data = await executeAgentAction<{
          success?: boolean
          message?: string
          error?: string
          data?: Record<string, unknown>
        }>({
          action: 'file_patch',
          params: { patch },
          confirm: true,
        })
        const nextStatus: AgentTaskStatus = data.success ? 'completed' : 'failed'
        setAgentTaskStatus(nextStatus)
        appendAgentTimeline(
          createAgentEvent('file_change', data.success ? 'Patch applied' : 'Patch apply failed', {
            tool_name: 'file_patch',
            description: data.message || data.error || 'Patch draft processed.',
            status: data.success ? 'completed' : 'failed',
            payload: {
              ...(data.data || { patch }),
              rerun_command: data.success ? recentFailedTestsCommand : undefined,
            },
          })
        )
        if (data.success && options?.rerunCommand?.trim()) {
          const patchedFiles = Array.isArray(data.data?.applied_files)
            ? data.data.applied_files.filter((file: unknown): file is string => typeof file === 'string')
            : []
          appendAgentTimeline(
            createAgentEvent('tool_call', 'Rerunning tests after patch', {
              tool_name: 'tests_run',
              description: options.rerunCommand,
              status: 'running',
              payload: { command: options.rerunCommand },
            })
          )

          const rerunData = await executeAgentAction<{
            success?: boolean
            message?: string
            error?: string
            data?: Record<string, unknown>
          }>({
            action: 'tests_run',
            params: { command: options.rerunCommand },
            confirm: true,
          })
          appendAgentTimeline(
            createAgentEvent('command_output', rerunData.success ? 'Tests rerun completed' : 'Tests rerun failed', {
              tool_name: 'tests_run',
              description: rerunData.message || rerunData.error || options.rerunCommand,
              status: rerunData.success ? 'completed' : 'failed',
              payload: rerunData.data || { command: options.rerunCommand },
            })
          )
          const verificationOutcome = buildVerificationOutcome(rerunData, {
            patchedFiles,
            rerunCommand: options.rerunCommand,
          })
          appendAgentTimeline(
            createAgentEvent('task_status', verificationOutcome.title, {
              description: verificationOutcome.description,
              status: verificationOutcome.status,
              payload: verificationOutcome.payload,
            })
          )

          const rerunStatus: AgentTaskStatus = rerunData.success ? 'completed' : 'failed'
          setAgentTaskStatus(rerunStatus)
          if (options?.autoFinalize && rerunData.success) {
            const testSummary =
              rerunData.data && typeof rerunData.data.test_summary === 'object' && rerunData.data.test_summary
                ? (rerunData.data.test_summary as {
                    passed?: number
                    failed?: number
                  })
                : null
            const automaticSummary = buildAutomaticRepairSummary({
              patchedFiles,
              rerunCommand: options.rerunCommand,
              passed: testSummary?.passed,
              failed: testSummary?.failed,
            })
            const automaticHandoff = buildAutomaticHandoffNote({
              patchedFiles,
              rerunCommand: options.rerunCommand,
              passed: testSummary?.passed,
              failed: testSummary?.failed,
            })
            appendAgentTimeline(
              createAgentEvent('assistant_message', 'Automatic repair completed', {
                description: automaticSummary,
                status: 'completed',
                payload: {
                  automatic_pipeline: 'repair_complete',
                  patched_files: patchedFiles,
                  rerun_command: options.rerunCommand,
                },
              })
            )
            appendAgentTimeline(
              createAgentEvent('task_status', 'Completion summary', {
                description: automaticSummary,
                status: 'completed',
                payload: {
                  completion_summary: automaticSummary,
                  patched_files: patchedFiles,
                  rerun_command: options.rerunCommand,
                },
              })
            )
            appendAgentTimeline(
              createAgentEvent('task_status', 'Handoff ready', {
                description: automaticHandoff,
                status: 'completed',
                payload: {
                  handoff_note: automaticHandoff,
                  patched_files: patchedFiles,
                  rerun_command: options.rerunCommand,
                },
              })
            )
          }
          const finalTestSummary =
            rerunData.data && typeof rerunData.data.test_summary === 'object' && rerunData.data.test_summary
              ? (rerunData.data.test_summary as {
                  passed?: number
                  failed?: number
                })
              : null
          appendAgentTimeline(
            createAgentEvent('task_status', rerunData.success ? 'Patch and test task completed' : 'Patch applied but tests failed', {
              status: rerunData.success ? 'completed' : 'failed',
              description:
                options?.autoFinalize && rerunData.success
                  ? buildAutomaticRepairSummary({
                      patchedFiles,
                      rerunCommand: options.rerunCommand,
                      passed: finalTestSummary?.passed,
                      failed: finalTestSummary?.failed,
                    })
                  : undefined,
              payload: {
                status: rerunStatus,
                automatic_pipeline: options?.autoFinalize ? 'repair_complete' : undefined,
                patched_files: patchedFiles,
                rerun_command: options.rerunCommand,
              },
            })
          )

          return {
            status: rerunStatus,
            timeline: [],
            summary: rerunData.message || rerunData.error || 'Patch applied and tests rerun.',
          }
        }

        appendAgentTimeline(
          createAgentEvent('task_status', data.success ? 'Patch task completed' : 'Patch task failed', {
            status: data.success ? 'completed' : 'failed',
            payload: { status: nextStatus },
          })
        )

        return {
          status: nextStatus,
          timeline: [],
          summary: data.message || data.error || 'Patch draft processed.',
        }
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : 'Applying patch draft failed.'
        setAgentTaskStatus('failed')
        appendAgentTimeline(
          createAgentEvent('task_status', 'Patch task failed', {
            description: errorMessage,
            status: 'failed',
            payload: { status: 'failed' },
          })
        )
        onError?.(errorMessage)
        return {
          status: 'failed',
          timeline: [],
          summary: errorMessage,
        }
      }
    },
    [appendAgentTimeline, onError, setAgentTaskStatus]
  )

  const confirmAgentAction = useCallback(async (): Promise<AgentRunResult | undefined> => {
    const pending = useChatStore.getState().pendingAgentConfirmation
    if (!pending) {
      return undefined
    }

    if (pending.action === 'file_patch' && typeof pending.params.patch === 'string') {
      setPendingAgentConfirmation(null)
      return applyPatchDraft(pending.params.patch, {
        rerunCommand:
          typeof pending.params.rerun_command === 'string' ? pending.params.rerun_command : undefined,
        autoFinalize: Boolean(pending.params.auto_finalize),
      })
    }

    setAgentTaskStatus('running')
    appendAgentTimeline(
      createAgentEvent('tool_call', `Confirmed ${pending.action}`, {
        tool_name: pending.action,
        description: pending.description,
        status: 'running',
        payload: pending.params,
      })
    )

    try {
      const data = await executeAgentAction<{
        success?: boolean
        message?: string
        error?: string
        data?: Record<string, unknown>
      }>({
        action: pending.action,
        params: pending.params,
        confirm: true,
      })
      const nextStatus: AgentTaskStatus = data.success ? 'completed' : 'failed'
      setPendingAgentConfirmation(null)
      setAgentTaskStatus(nextStatus)
      appendAgentTimeline(
        createAgentEvent('tool_result', data.success ? 'Confirmed action completed' : 'Confirmed action failed', {
          tool_name: pending.action,
          description: data.message || data.error || pending.description,
          status: data.success ? 'completed' : 'failed',
          payload: data.data || {},
        })
      )
      appendAgentTimeline(
        createAgentEvent('task_status', data.success ? 'Task completed' : 'Task failed', {
          status: data.success ? 'completed' : 'failed',
          payload: { status: nextStatus },
        })
      )
      return {
        status: nextStatus,
        timeline: [],
        summary: data.message || data.error || pending.description,
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Agent action failed.'
      setAgentTaskStatus('failed')
      appendAgentTimeline(
        createAgentEvent('task_status', 'Task failed', {
          description: errorMessage,
          status: 'failed',
          payload: { status: 'failed' },
        })
      )
      onError?.(errorMessage)
      return {
        status: 'failed',
        timeline: [],
        summary: errorMessage,
      }
    }
  }, [
    appendAgentTimeline,
    applyPatchDraft,
    onError,
    setAgentTaskStatus,
    setPendingAgentConfirmation,
  ])

  const cancelAgentAction = useCallback(() => {
    const pending = useChatStore.getState().pendingAgentConfirmation
    setPendingAgentConfirmation(null)
    setAgentTaskStatus('stopped')
    appendAgentTimeline(
      createAgentEvent('confirmation_request', 'Confirmation rejected', {
        description: pending?.description || 'The user rejected the pending action.',
        status: 'cancelled',
        payload: {
          action: pending?.action,
          status: 'cancelled',
        },
      })
    )
    appendAgentTimeline(
      createAgentEvent('task_status', 'Task stopped', {
        description: 'Execution stopped after confirmation was rejected.',
        status: 'cancelled',
        payload: { status: 'stopped' },
      })
    )
  }, [appendAgentTimeline, setAgentTaskStatus, setPendingAgentConfirmation])

  const stop = useCallback(() => {
    for (const controller of abortControllersRef.current.values()) {
      controller.abort()
    }
    abortControllersRef.current.clear()
    clearAllTimeouts()
    stopStreaming()
    setPendingAgentConfirmation(null)
    setAgentTaskStatus('stopped')
    setState((prev) => ({
      ...prev,
      status: 'stopped',
    }))
    onStatusChange?.('stopped')
  }, [clearAllTimeouts, onStatusChange, setAgentTaskStatus, setPendingAgentConfirmation, stopStreaming])

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
    runAgentTask,
    resumeAgentTask,
    resumeAgentFromEvent,
    confirmAgentAction,
    applyPatchDraft,
    cancelAgentAction,
    stop,
    retry,
    isStreaming: state.status === 'connecting' || state.status === 'streaming',
    isIdle: state.status === 'idle',
    isCompleted: state.status === 'completed',
    isError: state.status === 'error',
    isStopped: state.status === 'stopped',
  }
}
