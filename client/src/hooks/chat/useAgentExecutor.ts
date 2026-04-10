import { useCallback, useRef, useState } from 'react'
import { API_BASE_URL } from '../../services/api'
import { useChatStore } from '../../store/chatStore'

interface ExecutionTask {
  id: string
  action: string
  params: Record<string, unknown>
  originalMessage: string
  priority: 'high' | 'normal' | 'low'
  timestamp: number
}

interface ExecutionResult {
  success: boolean
  action: string
  result?: unknown
  error?: string
  duration_ms: number
}

interface AgentExecutorConfig {
  defaultTimeout?: number
  onExecutionStart?: (task: ExecutionTask) => void
  onExecutionComplete?: (result: ExecutionResult) => void
  onExecutionError?: (error: string, task: ExecutionTask) => void
  onConfirmRequired?: (task: ExecutionTask, message: string) => void
}

type ExecutorPhase = 'idle' | 'running' | 'waiting_confirm'

const DANGEROUS_ACTIONS = ['file_delete', 'file_write', 'system_command', 'app_close', 'window_close']
const WAITING_CONFIRM_ERROR = '等待用户确认'

function sortByPriority(tasks: ExecutionTask[]) {
  const priorityOrder = { high: 0, normal: 1, low: 2 }
  return [...tasks].sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority])
}

function createTaskId() {
  return `task_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
}

export function useAgentExecutor(config: AgentExecutorConfig = {}) {
  const {
    defaultTimeout = 30000,
    onExecutionStart,
    onExecutionComplete,
    onExecutionError,
    onConfirmRequired,
  } = config

  const [queue, setQueue] = useState<ExecutionTask[]>([])
  const [history, setHistory] = useState<ExecutionResult[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [phase, setPhase] = useState<ExecutorPhase>('idle')

  const queueRef = useRef<ExecutionTask[]>([])
  const pendingTaskRef = useRef<ExecutionTask | null>(null)
  const processingRef = useRef(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  const { agentExecution, setAgentExecution, currentSessionId } = useChatStore()

  const updateQueue = useCallback((updater: (prev: ExecutionTask[]) => ExecutionTask[]) => {
    setQueue((prev) => {
      const next = updater(prev)
      queueRef.current = next
      return next
    })
  }, [])

  const isDangerousAction = useCallback((action: string) => {
    return DANGEROUS_ACTIONS.some((rule) => action.toLowerCase().includes(rule))
  }, [])

  const addToQueue = useCallback(
    (task: Omit<ExecutionTask, 'id' | 'timestamp'>) => {
      const fullTask: ExecutionTask = { ...task, id: createTaskId(), timestamp: Date.now() }
      updateQueue((prev) => sortByPriority([...prev, fullTask]))
      return fullTask.id
    },
    [updateQueue]
  )

  const removeFromQueue = useCallback(
    (taskId: string) => {
      updateQueue((prev) => prev.filter((task) => task.id !== taskId))
    },
    [updateQueue]
  )

  const executeTask = useCallback(
    async (task: ExecutionTask): Promise<ExecutionResult> => {
      const startedAt = Date.now()
      onExecutionStart?.(task)
      setPhase('running')

      setAgentExecution({
        id: task.id,
        status: 'executing',
        action: task.action,
        description: `正在执行: ${task.action}`,
        params: task.params,
        timestamp: new Date().toISOString(),
      })

      abortControllerRef.current = new AbortController()
      const timeoutId = setTimeout(() => abortControllerRef.current?.abort(), defaultTimeout)

      try {
        const response = await fetch(`${API_BASE_URL}/agent/chat-execute`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: task.originalMessage,
            auto_confirm: false,
            context: task.params,
            session_id: currentSessionId,
          }),
          signal: abortControllerRef.current.signal,
        })

        clearTimeout(timeoutId)
        if (!response.ok) {
          const error = await response.json().catch(() => ({}))
          throw new Error(error.detail || '执行失败')
        }

        const data = await response.json()
        const duration_ms = Date.now() - startedAt

        if (data.result?.need_confirm) {
          pendingTaskRef.current = {
            ...task,
            params: {
              ...task.params,
              ...(data.result.params || {}),
              __original_message: task.originalMessage,
            },
          }

          setPhase('waiting_confirm')
          setAgentExecution({
            id: task.id,
            status: 'confirming',
            action: task.action,
            description: data.description || '需要确认此操作',
            params: pendingTaskRef.current.params,
            timestamp: new Date().toISOString(),
          })

          onConfirmRequired?.(task, data.description || '需要确认此操作')
          return { success: false, action: task.action, error: WAITING_CONFIRM_ERROR, duration_ms }
        }

        const result: ExecutionResult = {
          success: data.result?.success !== false,
          action: task.action,
          result: data.result,
          duration_ms,
        }

        setAgentExecution({
          id: task.id,
          status: 'completed',
          action: task.action,
          description: data.description || '执行完成',
          result: data.result,
          timestamp: new Date().toISOString(),
        })

        setTimeout(() => setAgentExecution(null), 3000)
        setPhase('idle')
        onExecutionComplete?.(result)
        return result
      } catch (error: unknown) {
        clearTimeout(timeoutId)
        const errorMsg =
          error instanceof Error ? (error.name === 'AbortError' ? '执行超时' : error.message) : '执行失败'
        const duration_ms = Date.now() - startedAt
        const result: ExecutionResult = {
          success: false,
          action: task.action,
          error: errorMsg,
          duration_ms,
        }

        setAgentExecution({
          id: task.id,
          status: 'failed',
          action: task.action,
          description: '执行失败',
          error: errorMsg,
          timestamp: new Date().toISOString(),
        })
        setTimeout(() => setAgentExecution(null), 5000)
        setPhase('idle')
        onExecutionError?.(errorMsg, task)
        return result
      }
    },
    [
      currentSessionId,
      defaultTimeout,
      onConfirmRequired,
      onExecutionComplete,
      onExecutionError,
      onExecutionStart,
      setAgentExecution,
    ]
  )

  const processQueue = useCallback(async () => {
    if (processingRef.current || queueRef.current.length === 0) return

    processingRef.current = true
    setIsProcessing(true)
    setPhase('running')

    try {
      while (queueRef.current.length > 0) {
        const currentTask = queueRef.current[0]
        if (!currentTask) break

        const result = await executeTask(currentTask)
        setHistory((prev) => [result, ...prev].slice(0, 100))
        removeFromQueue(currentTask.id)

        if (!result.success && result.error === WAITING_CONFIRM_ERROR) {
          break
        }
      }
    } finally {
      processingRef.current = false
      setIsProcessing(false)
      if (phase !== 'waiting_confirm') {
        setPhase('idle')
      }
    }
  }, [executeTask, phase, removeFromQueue])

  const confirmExecution = useCallback(async () => {
    if (!agentExecution || agentExecution.status !== 'confirming') return

    const pendingTask = pendingTaskRef.current
    const originalMessage =
      (pendingTask?.params?.['__original_message'] as string | undefined) ||
      (agentExecution.params?.['__original_message'] as string | undefined) ||
      agentExecution.action

    setPhase('running')
    setAgentExecution({
      ...agentExecution,
      status: 'executing',
    })

    const startedAt = Date.now()
    try {
      const response = await fetch(`${API_BASE_URL}/agent/chat-execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: originalMessage,
          auto_confirm: true,
          context: agentExecution.params,
          session_id: currentSessionId,
        }),
      })

      const data = await response.json()
      const result: ExecutionResult = {
        success: data.result?.success !== false,
        action: agentExecution.action,
        result: data.result,
        duration_ms: Date.now() - startedAt,
      }

      setAgentExecution({
        ...agentExecution,
        status: 'completed',
        result: data.result,
      })
      setTimeout(() => setAgentExecution(null), 3000)

      pendingTaskRef.current = null
      setHistory((prev) => [result, ...prev].slice(0, 100))
      onExecutionComplete?.(result)
      setPhase('idle')
      processQueue()
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : '确认执行失败'
      setAgentExecution({
        ...agentExecution,
        status: 'failed',
        error: errorMsg,
      })
      setTimeout(() => setAgentExecution(null), 5000)

      const result: ExecutionResult = {
        success: false,
        action: agentExecution.action,
        error: errorMsg,
        duration_ms: Date.now() - startedAt,
      }
      setHistory((prev) => [result, ...prev].slice(0, 100))
      setPhase('idle')
      onExecutionError?.(errorMsg, {
        id: agentExecution.id,
        action: agentExecution.action,
        params: agentExecution.params || {},
        originalMessage,
        priority: 'normal',
        timestamp: Date.now(),
      })
    }
  }, [agentExecution, currentSessionId, onExecutionComplete, onExecutionError, processQueue, setAgentExecution])

  const cancelExecution = useCallback(() => {
    abortControllerRef.current?.abort()
    pendingTaskRef.current = null
    updateQueue(() => [])
    setAgentExecution(null)
    processingRef.current = false
    setIsProcessing(false)
    setPhase('idle')
  }, [setAgentExecution, updateQueue])

  const execute = useCallback(
    async (
      action: string,
      params: Record<string, unknown> = {},
      options?: {
        priority?: 'high' | 'normal' | 'low'
        skipQueue?: boolean
      }
    ) => {
      const task: Omit<ExecutionTask, 'id' | 'timestamp'> = {
        action,
        params,
        originalMessage: (params.message as string | undefined) || action,
        priority: options?.priority || 'normal',
      }

      if (options?.skipQueue || isDangerousAction(action)) {
        const directTask: ExecutionTask = { ...task, id: createTaskId(), timestamp: Date.now() }
        const result = await executeTask(directTask)
        setHistory((prev) => [result, ...prev].slice(0, 100))
        return result
      }

      const taskId = addToQueue(task)
      setTimeout(processQueue, 0)
      return { taskId, queued: true }
    },
    [addToQueue, executeTask, isDangerousAction, processQueue]
  )

  const executeFromMessage = useCallback(
    async (
      message: string,
      context?: Record<string, unknown>
    ): Promise<{ executed: boolean; result?: unknown; error?: string }> => {
      try {
        const response = await fetch(`${API_BASE_URL}/agent/chat-execute`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message,
            auto_confirm: false,
            context,
            session_id: currentSessionId,
          }),
        })

        const data = await response.json()
        if (!data.detected) return { executed: false }

        if (data.result?.need_confirm) {
          setPhase('waiting_confirm')
          setAgentExecution({
            id: `exec_${Date.now()}`,
            status: 'confirming',
            action: data.action,
            description: data.description || '需要确认此操作',
            params: {
              ...(data.result.params || {}),
              __original_message: message,
            },
            timestamp: new Date().toISOString(),
          })
          return { executed: true, result: { need_confirm: true } }
        }

        setAgentExecution({
          id: `exec_${Date.now()}`,
          status: 'completed',
          action: data.action,
          description: data.description || '执行完成',
          result: data.result,
          timestamp: new Date().toISOString(),
        })
        setTimeout(() => setAgentExecution(null), 3000)
        setPhase('idle')
        return { executed: true, result: data.result }
      } catch (error: unknown) {
        const errorMsg = error instanceof Error ? error.message : '执行失败'
        return { executed: false, error: errorMsg }
      }
    },
    [currentSessionId, setAgentExecution]
  )

  const clearHistory = useCallback(() => setHistory([]), [])

  return {
    queue,
    history,
    isProcessing,
    phase,
    agentExecution,
    execute,
    executeFromMessage,
    confirmExecution,
    cancelExecution,
    clearHistory,
    isConfirming: agentExecution?.status === 'confirming',
    isExecuting: agentExecution?.status === 'executing',
  }
}
