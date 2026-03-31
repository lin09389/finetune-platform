import { useState, useCallback, useRef, useEffect } from 'react'
import { useChatStore } from '../../store/chatStore'
import { API_BASE_URL } from '../../services/api'
import type { KnowledgeSource, RetrievalInfo } from '../../types'

interface StreamConfig {
  maxRetries?: number
  retryDelay?: number
  timeout?: number
  onChunk?: (chunk: string, fullContent: string) => void
  onComplete?: (content: string, metadata?: StreamMetadata) => void
  onError?: (error: string) => void
  onStatusChange?: (status: StreamState['status']) => void
}

interface StreamMetadata {
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
    retrieval_time: number
  }
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
    messages,
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
          error: '请求超时',
        }))
        onStatusChange?.('error')
        onError?.('请求超时')
      }
    }, timeout)
  }, [timeout, clearTimeouts, onStatusChange, onError])

  const buildChatHistory = useCallback(() => {
    return messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .filter((m) => !m.isLoading)
      .map((m) => ({ role: m.role, content: m.content }))
  }, [messages])

  const sendMessage = useCallback(async (content: string, options?: {
    systemPrompt?: string
    knowledgeOverride?: { enabled: boolean; collectionId?: string }
    memoryOverride?: { enabled: boolean }
  }) => {
    if (!content.trim()) return

    addMessage({
      role: 'user',
      content: content.trim(),
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
      const chatHistory = buildChatHistory()
      chatHistory.push({ role: 'user', content: content.trim() })

      const useKnowledge = options?.knowledgeOverride?.enabled ?? settings.useKnowledge
      const knowledgeCollection = options?.knowledgeOverride?.collectionId ?? settings.knowledgeCollection
      const useMemory = options?.memoryOverride?.enabled ?? settings.useMemory

      const response = await fetch(`${API_BASE_URL}/inference/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: settings.modelId,
          messages: chatHistory,
          options: {
            max_tokens: settings.maxTokens,
            temperature: settings.temperature,
            backend: settings.backend,
          },
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
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      const fullContent = data.message?.content || data.text || ''

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
      
      const metadata: StreamMetadata = {
        knowledgeSources: data.knowledge_sources,
        retrievalInfo: data.retrieval_info,
        memoryContext: data.memory_context,
        unifiedContext: data.unified_context,
      }
      
      updateMessage(assistantMessageId, {
        knowledge_sources: metadata.knowledgeSources,
        retrieval_info: metadata.retrievalInfo,
      })

      completeStreaming()

      onComplete?.(fullContent, metadata)
      retryCountRef.current = 0

      if (currentSessionId) {
        await fetch(`${API_BASE_URL}/chat/sessions/${currentSessionId}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [
              { role: 'user', content: content.trim() },
              { role: 'assistant', content: fullContent },
            ],
          }),
        }).catch(console.error)
      }

    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        setState((prev) => ({
          ...prev,
          status: 'stopped',
        }))
        onStatusChange?.('stopped')
        stopStreaming()
        updateMessage(assistantMessageId, {
          content: lastContentRef.current + '\n\n（已停止生成）',
          isLoading: false,
        })
        return
      }

      const errorMsg = error instanceof Error ? error.message : '请求失败'
      
      if (retryCountRef.current < maxRetries) {
        retryCountRef.current++
        setState((prev) => ({
          ...prev,
          status: 'connecting',
          error: `重试中 (${retryCountRef.current}/${maxRetries})...`,
        }))
        
        setTimeout(() => {
          sendMessage(content, options)
        }, retryDelay * retryCountRef.current)
        return
      }

      setState((prev) => ({
        ...prev,
        status: 'error',
        error: errorMsg,
      }))
      onStatusChange?.('error')
      onError?.(errorMsg)

      updateMessage(assistantMessageId, {
        content: `错误: ${errorMsg}`,
        isLoading: false,
      })
      completeStreaming()
    } finally {
      clearTimeouts()
      abortControllerRef.current = null
    }
  }, [
    addMessage,
    startStreaming,
    updateStreamingContent,
    stopStreaming,
    completeStreaming,
    updateMessage,
    settings,
    messages,
    currentSessionId,
    maxRetries,
    retryDelay,
    buildChatHistory,
    startTimeout,
    clearTimeouts,
    onComplete,
    onError,
    onStatusChange,
  ])

  const sendCloudMessage = useCallback(async (content: string, cloudConfig: {
    provider: string
    apiKey?: string
    keyId?: string
    model: string
    groupId?: string
    baseUrl?: string
  }) => {
    if (!content.trim()) return

    addMessage({
      role: 'user',
      content: content.trim(),
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
      const chatHistory = buildChatHistory()
      chatHistory.push({ role: 'user', content: content.trim() })

      let knowledgeContext = ''
      if (settings.useKnowledge && settings.knowledgeCollection) {
        try {
          const ragResponse = await fetch(`${API_BASE_URL}/knowledge/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              collection_id: settings.knowledgeCollection,
              query: content,
              top_k: 5,
            }),
          })
          if (ragResponse.ok) {
            const ragData = await ragResponse.json()
            if (ragData.results?.length > 0) {
              knowledgeContext = '\n\n[知识库相关信息]\n' + 
                ragData.results.map((r: { content: string }) => r.content).join('\n\n')
            }
          }
        } catch (e) {
          console.warn('知识库检索失败:', e)
        }
      }

      if (knowledgeContext) {
        chatHistory[chatHistory.length - 1] = {
          role: 'user',
          content: `请参考以下信息回答问题：${knowledgeContext}\n\n问题：${content}`,
        }
      }

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
          messages: chatHistory,
          stream: true,
        }),
        signal: abortControllerRef.current.signal,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({}))
        throw new Error(error.detail || '云端 AI 调用失败')
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('无法读取响应流')
      }

      const decoder = new TextDecoder()
      let fullContent = ''

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
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') continue

            try {
              const parsed = JSON.parse(data)
              
              if (parsed.error) {
                throw new Error(parsed.error)
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
      }

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

      completeStreaming()
      onComplete?.(fullContent)

    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        setState((prev) => ({
          ...prev,
          status: 'stopped',
        }))
        onStatusChange?.('stopped')
        stopStreaming()
        updateMessage(assistantMessageId, {
          content: lastContentRef.current + '\n\n（已停止生成）',
          isLoading: false,
        })
        return
      }

      const errorMsg = error instanceof Error ? error.message : '云端 AI 调用失败'
      
      setState((prev) => ({
        ...prev,
        status: 'error',
        error: errorMsg,
      }))
      onStatusChange?.('error')
      onError?.(errorMsg)

      updateMessage(assistantMessageId, {
        content: `错误：${errorMsg}`,
        isLoading: false,
      })
      completeStreaming()
    } finally {
      clearTimeouts()
      abortControllerRef.current = null
    }
  }, [
    addMessage,
    startStreaming,
    updateStreamingContent,
    stopStreaming,
    completeStreaming,
    updateMessage,
    settings,
    buildChatHistory,
    startTimeout,
    clearTimeouts,
    onChunk,
    onComplete,
    onError,
    onStatusChange,
  ])

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
  }, [stopStreaming, clearTimeouts, onStatusChange])

  const retry = useCallback(() => {
    retryCountRef.current = 0
    const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user')
    if (lastUserMessage) {
      sendMessage(lastUserMessage.content)
    }
  }, [messages, sendMessage])

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
