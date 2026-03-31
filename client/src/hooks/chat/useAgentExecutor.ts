import { useState, useCallback, useRef } from 'react'
import { useChatStore } from '../../store/chatStore'
import { API_BASE_URL } from '../../services/api'

interface ExecutionTask {
  id: string
  action: string
  params: Record<string, unknown>
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
  maxConcurrent?: number
  defaultTimeout?: number
  onExecutionStart?: (task: ExecutionTask) => void
  onExecutionComplete?: (result: ExecutionResult) => void
  onExecutionError?: (error: string, task: ExecutionTask) => void
  onConfirmRequired?: (task: ExecutionTask, message: string) => void
}

const DANGEROUS_ACTIONS = [
  'file_delete',
  'file_write',
  'system_command',
  'app_close',
  'window_close',
]

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

  const processingRef = useRef(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  const {
    agentExecution,
    setAgentExecution,
    currentSessionId,
  } = useChatStore()

  const isDangerousAction = useCallback((action: string) => {
    return DANGEROUS_ACTIONS.some((da) => action.toLowerCase().includes(da))
  }, [])

  const addToQueue = useCallback((task: Omit<ExecutionTask, 'id' | 'timestamp'>) => {
    const newTask: ExecutionTask = {
      ...task,
      id: `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
    }

    setQueue((prev) => {
      const newQueue = [...prev, newTask]
      newQueue.sort((a, b) => {
        const priorityOrder = { high: 0, normal: 1, low: 2 }
        return priorityOrder[a.priority] - priorityOrder[b.priority]
      })
      return newQueue
    })

    return newTask.id
  }, [])

  const removeFromQueue = useCallback((taskId: string) => {
    setQueue((prev) => prev.filter((t) => t.id !== taskId))
  }, [])

  const executeTask = useCallback(async (task: ExecutionTask): Promise<ExecutionResult> => {
    const startTime = Date.now()

    onExecutionStart?.(task)

    setAgentExecution({
      id: task.id,
      status: 'executing',
      action: task.action,
      description: `正在执行: ${task.action}`,
      params: task.params,
      timestamp: new Date().toISOString(),
    })

    abortControllerRef.current = new AbortController()

    const timeoutId = setTimeout(() => {
      abortControllerRef.current?.abort()
    }, defaultTimeout)

    try {
      const message = task.params?.['message'] || task.action
      const response = await fetch(`${API_BASE_URL}/agent/chat-execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
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
      const duration_ms = Date.now() - startTime

      if (data.result?.need_confirm) {
        setAgentExecution({
          id: task.id,
          status: 'confirming',
          action: task.action,
          description: data.description || '需要确认此操作',
          params: data.result.params,
          timestamp: new Date().toISOString(),
        })

        onConfirmRequired?.(task, data.description || '需要确认此操作')

        return {
          success: false,
          action: task.action,
          error: '等待用户确认',
          duration_ms,
        }
      }

      const result: ExecutionResult = {
        success: !data.result?.success === false,
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

      onExecutionComplete?.(result)

      return result

    } catch (error: unknown) {
      clearTimeout(timeoutId)
      
      const errorMsg = error instanceof Error 
        ? (error.name === 'AbortError' ? '执行超时' : error.message)
        : '执行失败'

      const duration_ms = Date.now() - startTime

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

      onExecutionError?.(errorMsg, task)

      return result
    }
  }, [defaultTimeout, currentSessionId, setAgentExecution, onExecutionStart, onExecutionComplete, onExecutionError, onConfirmRequired])

  const processQueue = useCallback(async () => {
    if (processingRef.current || queue.length === 0) return

    processingRef.current = true
    setIsProcessing(true)

    try {
      while (queue.length > 0) {
        const task = queue[0]
        if (!task) break
        
        const result = await executeTask(task)
        
        setHistory((prev) => [result, ...prev].slice(0, 100))
        removeFromQueue(task.id)

        if (result.success === false && result.error === '等待用户确认') {
          break
        }
      }
    } finally {
      processingRef.current = false
      setIsProcessing(false)
    }
  }, [queue, executeTask, removeFromQueue])

  const confirmExecution = useCallback(async () => {
    if (!agentExecution || agentExecution.status !== 'confirming') return

    setAgentExecution({
      ...agentExecution,
      status: 'executing',
    })

    const startTime = Date.now()

    try {
      const response = await fetch(`${API_BASE_URL}/agent/chat-execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: agentExecution.action,
          auto_confirm: true,
          context: agentExecution.params,
          session_id: currentSessionId,
        }),
      })

      const data = await response.json()
      const duration_ms = Date.now() - startTime

      const result: ExecutionResult = {
        success: !data.result?.success === false,
        action: agentExecution.action,
        result: data.result,
        duration_ms,
      }

      setAgentExecution({
        ...agentExecution,
        status: 'completed',
        result: data.result,
      })

      setTimeout(() => setAgentExecution(null), 3000)

      setHistory((prev) => [result, ...prev].slice(0, 100))
      onExecutionComplete?.(result)

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
        duration_ms: Date.now() - startTime,
      }

      setHistory((prev) => [result, ...prev].slice(0, 100))
      onExecutionError?.(errorMsg, {
        id: agentExecution.id,
        action: agentExecution.action,
        params: agentExecution.params || {},
        priority: 'normal',
        timestamp: Date.now(),
      })
    }
  }, [agentExecution, currentSessionId, setAgentExecution, onExecutionComplete, onExecutionError, processQueue])

  const cancelExecution = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    setAgentExecution(null)
    setQueue([])
    processingRef.current = false
    setIsProcessing(false)
  }, [setAgentExecution])

  const execute = useCallback(async (
    action: string,
    params: Record<string, unknown> = {},
    options?: {
      priority?: 'high' | 'normal' | 'low'
      skipQueue?: boolean
      requireConfirm?: boolean
    }
  ) => {
    const task: Omit<ExecutionTask, 'id' | 'timestamp'> = {
      action,
      params,
      priority: options?.priority || 'normal',
    }

    if (options?.skipQueue || isDangerousAction(action)) {
      const fullTask: ExecutionTask = {
        ...task,
        id: `task_${Date.now()}`,
        timestamp: Date.now(),
      }
      const result = await executeTask(fullTask)
      setHistory((prev) => [result, ...prev].slice(0, 100))
      return result
    }

    const taskId = addToQueue(task)
    
    setTimeout(processQueue, 0)

    return { taskId, queued: true }
  }, [addToQueue, executeTask, isDangerousAction, processQueue])

  const executeFromMessage = useCallback(async (
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

      if (!data.detected) {
        return { executed: false }
      }

      if (data.result?.need_confirm) {
        setAgentExecution({
          id: `exec_${Date.now()}`,
          status: 'confirming',
          action: data.action,
          description: data.description || '需要确认此操作',
          params: data.result.params,
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

      return { executed: true, result: data.result }

    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : '执行失败'
      return { executed: false, error: errorMsg }
    }
  }, [currentSessionId, setAgentExecution])

  const clearHistory = useCallback(() => {
    setHistory([])
  }, [])

  return {
    queue,
    history,
    isProcessing,
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
