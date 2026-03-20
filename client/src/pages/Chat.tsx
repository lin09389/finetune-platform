import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Select, Input, Button, Space, Badge, Dropdown, Modal, App, Avatar, Typography, Alert, Switch, Tooltip } from 'antd'
import { SendOutlined, PlusOutlined, ExportOutlined, MoreOutlined, ClearOutlined, HistoryOutlined, RobotOutlined, ThunderboltOutlined, BulbOutlined, CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined, ThunderboltFilled, CloudOutlined, BookOutlined, SunOutlined, MoonOutlined } from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../store/appStore'
import { streamInference, getBackends, switchBackend, getOllamaStatus, getInferenceModels, chatExecuteAgent, getModelList, API_BASE_URL } from '../services/api'
import ChatMessage from '../components/ChatMessage'
import ChatHistoryDrawer from '../components/ChatHistoryDrawer'
import MemoryManager from '../components/MemoryManager'
import APIKeyManager from './APIKeyManager'
import { ConnectionStatus, PartialSaveIndicator } from '../components/ConnectionStatus'
import { StopButton, StreamingIndicator, InterruptedContentBanner } from '../components/StopButton'
import { useStreamResponse, getSavedPartials, deletePartial } from '../hooks/useStreamResponse'
import type { PartialResponse } from '../hooks/useStreamResponse'
import type { ChatMessage as ChatMessageType, KnowledgeSource, RetrievalInfo } from '../types'
import { Virtuoso } from 'react-virtuoso'
import { useTheme } from '../theme'
import { transitions } from '../theme/animations'

// 防抖函数
function debounce<T extends (...args: any[]) => any>(fn: T, delay: number): T {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  return ((...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => fn(...args), delay)
  }) as T
}

// 云端 AI 配置类型
interface APIKeyConfig {
  provider: string
  api_key?: string  // 可选，因为可以使用 key_id
  model?: string
  key_id?: string  // 后端加密存储的 Key ID
  group_id?: string  // Group ID（用于 Minimax）
  base_url?: string  // 自定义 Base URL
}

const { TextArea } = Input
const { Title, Text } = Typography

interface Message extends ChatMessageType {
  id: string
  knowledge_sources?: KnowledgeSource[]
  retrieval_info?: RetrievalInfo
}

// Agent 执行状态
interface AgentExecution {
  status: 'pending' | 'executing' | 'completed' | 'failed' | 'confirm'
  action?: string
  description?: string
  result?: any
  error?: string
}

export default function Chat() {
  const { message } = App.useApp()
  const { setModels, chatSessionId, chatMessages, chatModelId, chatBackend, setChatSessionId, setChatMessages, addChatMessage, updateChatMessage, clearChatSession } = useAppStore()
  const { theme, toggleTheme } = useTheme()
  
  const messages = chatMessages
  const currentSessionId = chatSessionId
  
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentBackend, setCurrentBackend] = useState<string>(chatBackend || 'ollama')
  const [backends, setBackends] = useState<any[]>([])
  const [ollamaModels, setOllamaModels] = useState<{ id: string; name: string }[]>([])
  const [hfModels, setHfModels] = useState<{ id: string; name: string }[]>([])
  const [selectedModel, setSelectedModel] = useState<string | undefined>(chatModelId || undefined)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [sessions, setSessions] = useState<any[]>([])

  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false)
  const [memoryHint, setMemoryHint] = useState<string[]>([])

  // Agent 相关状态
  const [agentExecution, setAgentExecution] = useState<AgentExecution | null>(null)
  const [pendingConfirm, setPendingConfirm] = useState<{ action: string; params: any; message: string } | null>(null)

  // 云端 AI 相关状态
  const [useCloudAI, setUseCloudAI] = useState(false)
  const [cloudAIConfig, setCloudAIConfig] = useState<APIKeyConfig | null>(null)
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [cloudModels, setCloudModels] = useState<{ value: string; label: string }[]>([])
  const [selectedCloudModel, setSelectedCloudModel] = useState<string>('MiniMax-M2.5')

  // 知识库相关状态
  const [useKnowledge, setUseKnowledge] = useState(false)
  const [selectedCollection, setSelectedCollection] = useState<string>()
  const [collections, setCollections] = useState<{ id: string; name: string; count: number }[]>([])
  const [autoRetrieve, setAutoRetrieve] = useState(true)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const sessionIdCounter = useRef(0)
  const textareaRef = useRef<any>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const {
    state: streamState,
    partialResponse,
    isStreaming,
    stop: stopStream,
    savePartial,
    resume: resumeStream,
    reset: resetStream,
    getStats,
  } = useStreamResponse({
    autoSave: true,
    saveInterval: 5000,
    maxRetries: 3,
    onChunk: (_chunk, fullContent) => {
      if (currentStreamingMessageId) {
        updateChatMessage(currentStreamingMessageId, {
          content: fullContent,
          isLoading: false,
        })
      }
    },
    onComplete: (content) => {
      if (currentStreamingMessageId) {
        updateChatMessage(currentStreamingMessageId, {
          content: content,
          isLoading: false,
        })
      }
      setCurrentStreamingMessageId(null)
      setLoading(false)
    },
    onError: (error) => {
      message.error(`流式响应错误: ${error}`)
    },
    onReconnecting: (retryCount) => {
      message.warning(`正在重连... (第 ${retryCount} 次)`)
    },
    onPartialSave: (partial) => {
      setLastPartialSave(partial)
    },
  })

  const [currentStreamingMessageId, setCurrentStreamingMessageId] = useState<string | null>(null)
  const [lastPartialSave, setLastPartialSave] = useState<PartialResponse | null>(null)
  const [showInterruptedBanner, setShowInterruptedBanner] = useState(false)

  // 虚拟滚动阈值：消息超过此数量时启用虚拟滚动
  const VIRTUAL_SCROLL_THRESHOLD = 100

  // 判断是否启用虚拟滚动
  const enableVirtualScroll = useMemo(() => {
    return messages.length > VIRTUAL_SCROLL_THRESHOLD
  }, [messages.length])

  // 保存消息到后端的防抖函数
  const saveMessagesToBackend = useCallback(
    debounce(async (sessionId: string | null, msgs: ChatMessageType[]) => {
      if (!sessionId || msgs.length === 0) return
      
      try {
        await fetch(`${API_BASE_URL}/chat/session/${sessionId}/message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: msgs })
        })
      } catch (error) {
        console.error('Failed to save messages:', error)
      }
    }, 1000),
    []
  )

  // 自动保存消息到后端
  useEffect(() => {
    if (currentSessionId && messages.length > 0) {
      saveMessagesToBackend(currentSessionId, messages)
    }
  }, [messages, currentSessionId, saveMessagesToBackend])

  // 恢复上次活跃会话
  useEffect(() => {
    const restoreSession = async () => {
      if (currentSessionId) {
        try {
          const response = await fetch(`${API_BASE_URL}/chat/session/${currentSessionId}`)
          if (response.ok) {
            const data = await response.json()
            if (data.messages && data.messages.length > 0) {
              setChatMessages(data.messages)
            }
          } else {
            // 会话不存在，清除 localStorage 中的无效 sessionId
            console.warn('Session not found, clearing sessionId')
            setChatSessionId(null)
          }
        } catch (error) {
          console.error('Failed to restore session:', error)
        }
      }
    }

    restoreSession()
  }, [currentSessionId, setChatSessionId, setChatMessages])

  // 加载初始数据
  useEffect(() => {
    // 使用 Promise.allSettled 确保即使某个请求失败，其他请求仍会执行
    Promise.allSettled([
      loadBackends(),
      loadModels(),
      loadHistory(),
      loadCloudAIConfig(),
      loadCollections()
    ]).then((results) => {
      // 统计失败的请求
      const failed = results.filter(r => r.status === 'rejected')
      if (failed.length > 0) {
        console.warn(`${failed.length} 个初始请求失败，请检查后端是否运行`)
      }
    })

    // 加载已保存的部分响应
    const partials = getSavedPartials()
    if (partials.length > 0) {
      console.log(`发现 ${partials.length} 个已保存的部分响应`)
    }
  }, [])  // 空依赖 - 仅在挂载时执行一次

  const loadModels = async () => {
    try {
      const list = await getModelList()
      setModels(list)
    } catch (error) {
      console.error('Failed to load models:', error)
    }
  }

  const loadCollections = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/collections`)
      if (response.ok) {
        const data = await response.json()
        setCollections(data.collections.map((c: any) => ({
          id: c.name,
          name: c.name,
          count: c.count
        })))
      }
    } catch (error) {
      console.error('Failed to load collections:', error)
    }
  }

  // 加载云端 AI 配置
  const loadCloudAIConfig = async () => {
    // 首先尝试从后端加载已保存的 API Key
    try {
      const response = await fetch(`${API_BASE_URL}/cloud/api-keys`)
      if (response.ok) {
        const data = await response.json()
        if (data.keys && data.keys.length > 0) {
          // 使用第一个已保存的 key
          const firstKey = data.keys[0]
          const keyData = await fetch(`${API_BASE_URL}/cloud/api-keys/${firstKey.id}/data`).then(r => r.json()).catch(() => ({}))
          
          const config: APIKeyConfig = {
            provider: firstKey.provider,
            api_key: '',  // 不存明文
            key_id: firstKey.id,
            model: 'MiniMax-M2.5',
            group_id: keyData.group_id || '',
            base_url: keyData.base_url || ''
          }
          setCloudAIConfig(config)
          setUseCloudAI(true)
          loadCloudModels(config.provider)
          setSelectedCloudModel('MiniMax-M2.5')
          return
        }
      }
    } catch (e) {
      console.log('从后端加载配置失败，尝试 localStorage')
    }
    
    // 回退到 localStorage
    const saved = localStorage.getItem('cloud_ai_config')
    if (saved) {
      try {
        const config = JSON.parse(saved)
        setCloudAIConfig(config)
        if (config.api_key || config.key_id) {
          setUseCloudAI(true)
        }
        loadCloudModels(config.provider)
        if (config.model) {
          setSelectedCloudModel(config.model)
        }
      } catch (e) {
        console.error('加载云端 AI 配置失败:', e)
      }
    }
  }

  // 加载云端模型选项
  const loadCloudModels = (provider: string) => {
    const MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
      'minimax-coding': [
        { value: 'MiniMax-M2.5', label: 'MiniMax-M2.5 (Coding Plan 推荐)' },
        { value: 'MiniMax-Text-01', label: 'MiniMax-Text-01' },
        { value: 'abab6.5s-chat', label: 'abab6.5s-chat' },
      ],
      'minimax': [
        { value: 'MiniMax-M2.5', label: 'MiniMax-M2.5 (推荐)' },
        { value: 'MiniMax-M2.5-highspeed', label: 'MiniMax-M2.5-highspeed (高速)' },
        { value: 'MiniMax-Text-01', label: 'MiniMax-Text-01' },
        { value: 'abab6.5s-chat', label: 'abab6.5s-chat (快速)' },
        { value: 'abab6.5g-chat', label: 'abab6.5g-chat (通用)' },
      ],
      'glm': [
        { value: 'glm-4', label: 'glm-4 (最强)' },
        { value: 'glm-3-turbo', label: 'glm-3-turbo (快速)' },
        { value: 'glm-4v', label: 'glm-4v (多模态)' },
      ],
    }
    const models = MODEL_OPTIONS[provider] || []
    setCloudModels(models)
    if (models.length > 0 && !selectedCloudModel) {
      const firstModel = models[0]?.value
      if (firstModel) {
        setSelectedCloudModel(firstModel)
      }
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const loadBackends = async () => {
    try {
      const data = await getBackends()
      setCurrentBackend(data.current)
      setBackends(data.backends)

      if (data.current === 'ollama') {
        const ollamaStatus = await getOllamaStatus()
        setOllamaModels(ollamaStatus.models.map((m: { name: string }) => ({
          id: m.name,
          name: m.name
        })))
        if (!selectedModel && ollamaStatus.models.length > 0) {
          setSelectedModel(ollamaStatus.models[0].name)
        }
      } else {
        const models = await getInferenceModels()
        setHfModels(models.map((m: any) => ({
          id: m.id,
          name: m.name || m.id
        })))
        if (!selectedModel && models.length > 0) {
          setSelectedModel(models[0].id)
        }
      }
    } catch (error) {
      console.error('Failed to load backends:', error)
    }
  }

  const loadHistory = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat`)
      if (response.ok) {
        const data = await response.json()
        setSessions(data.sessions || [])
        console.log('Loaded sessions:', data.sessions?.length || 0)
      } else {
        console.error('Failed to load history:', response.status, response.statusText)
      }
    } catch (error) {
      console.error('Failed to load history:', error)
    }
  }

  const handleBackendChange = async (backend: string) => {
    try {
      await switchBackend(backend)
      setCurrentBackend(backend)
      setSelectedModel(undefined)

      if (backend === 'ollama') {
        const ollamaStatus = await getOllamaStatus()
        setOllamaModels(ollamaStatus.models.map((m: { name: string }) => ({
          id: m.name,
          name: m.name
        })))
        if (ollamaStatus.models.length > 0) {
          setSelectedModel(ollamaStatus.models[0].name)
        }
      } else {
        const models = await getInferenceModels()
        setHfModels(models.map((m: any) => ({
          id: m.id,
          name: m.name || m.id
        })))
        if (models.length > 0) {
          setSelectedModel(models[0].id)
        }
      }
      message.success(`已切换到 ${backend === 'ollama' ? 'Ollama' : 'HuggingFace'} 后端`)
    } catch {
      message.error('切换失败')
    }
  }

  const createNewSession = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '新对话', model_id: selectedModel || '' })
      })
      if (response.ok) {
        const data = await response.json()
        setChatSessionId(data.id)
        setChatMessages([])
        await loadHistory()
        message.success('新对话已创建')
      }
    } catch (error) {
      console.error('Failed to create session:', error)
      sessionIdCounter.current += 1
      const newId = `local_${sessionIdCounter.current}`
      setChatSessionId(newId)
      setChatMessages([])
    }
  }

  const loadSession = async (sessionId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/session/${sessionId}`)
      if (response.ok) {
        const data = await response.json()
        setChatSessionId(sessionId)
        setChatMessages(data.messages || [])
        setHistoryOpen(false)
      }
    } catch (error) {
      console.error('Failed to load session:', error)
    }
  }

  const deleteSession = async (sessionId: string) => {
    try {
      await fetch(`${API_BASE_URL}/chat/session/${sessionId}`, { method: 'DELETE' })
      await loadHistory()
      if (currentSessionId === sessionId) {
        clearChatSession()
      }
      message.success('对话已删除')
    } catch (error) {
      console.error('Failed to delete session:', error)
    }
  }

  // 记忆提取函数
  const extractMemory = async (content: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/memory/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, role: 'user' })
      })
      const data = await response.json()

      if (data.extracted > 0) {
        // 显示记忆提示
        setMemoryHint(data.memories.map((m: { content: string }) => m.content))
        setTimeout(() => setMemoryHint([]), 5000)
      }
    } catch (error) {
      // 提取失败不影响聊天
      console.warn('记忆提取失败:', error)
    }
  }

  // Agent 执行函数
  const executeAgent = async (
    userMessage: string, 
    context?: { content?: string; content_type?: string; generated_filename?: string }
  ): Promise<{ executed: boolean; result?: any }> => {
    try {
      setAgentExecution({ status: 'executing' })
      
      const result = await chatExecuteAgent(userMessage, false, context)
      
      if (result.detected) {
        // 检查是否需要确认
        if (result.result?.need_confirm) {
          setAgentExecution({ status: 'confirm', action: result.action, description: result.description })
          setPendingConfirm({ action: result.action, params: result.result.params, message: userMessage })
          return { executed: true, result: { need_confirm: true } }
        }
        
        // 执行成功
        setAgentExecution({ 
          status: 'completed', 
          action: result.action, 
          description: result.description,
          result: result.result 
        })
        
        // 2秒后清除状态
        setTimeout(() => setAgentExecution(null), 3000)
        
        return { executed: true, result: result.result }
      }
      
      setAgentExecution(null)
      return { executed: false }
      
    } catch (error) {
      console.error('Agent 执行失败:', error)
      setAgentExecution({ status: 'failed', error: String(error) })
      setTimeout(() => setAgentExecution(null), 3000)
      return { executed: false }
    }
  }

  // Skill 意图检测和执行
  const detectAndExecuteSkill = async (userMessage: string): Promise<{ executed: boolean; result?: any }> => {
    const skillPatterns: Record<string, { pattern: RegExp; skillName: string; extractParams: (match: RegExpMatchArray) => Record<string, any> }> = {
      file_read: {
        pattern: /(?:读取|查看|打开|显示)(.+?)文件|(?:读取|查看|打开|显示)(.+?\.\w+)/i,
        skillName: 'file_read',
        extractParams: (match) => ({ file_path: (match[1] || match[2] || '').trim() })
      },
      file_list: {
        pattern: /(?:列出|查看|显示)(.+?)目录|(?:列出|查看|显示)(.+?)文件夹|ls\s+(.+)/i,
        skillName: 'file_list',
        extractParams: (match) => ({ directory: (match[1] || match[2] || match[3] || '.').trim() })
      },
      system_info: {
        pattern: /(?:系统信息|系统状态|system info|系统概况)/i,
        skillName: 'system_info',
        extractParams: () => ({})
      },
      calculator: {
        pattern: /(?:计算|算一下|等于多少)\s*(.+)/i,
        skillName: 'calculator',
        extractParams: (match) => ({ expression: (match[1] || '').trim() })
      },
      json_parse: {
        pattern: /(?:解析|parse)\s*(?:json)?\s*(.+)/i,
        skillName: 'json_parse',
        extractParams: (match) => ({ json_string: (match[1] || '').trim() })
      }
    }

    for (const config of Object.values(skillPatterns)) {
      const match = userMessage.match(config.pattern)
      if (match) {
        try {
          const params = config.extractParams(match)
          
          const response = await fetch(`${API_BASE_URL}/skills/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              skill_name: config.skillName,
              parameters: params
            })
          })

          if (response.ok) {
            const result = await response.json()
            return { executed: true, result }
          }
        } catch (e) {
          console.warn(`Skill ${config.skillName} 执行失败:`, e)
        }
      }
    }

    return { executed: false }
  }

  // 确认危险操作
  const confirmDangerousAction = async () => {
    if (!pendingConfirm) return
    
    setAgentExecution({ status: 'executing' })
    
    try {
      const result = await chatExecuteAgent(pendingConfirm.message, true)
      
      setAgentExecution({ 
        status: 'completed', 
        action: result.action, 
        description: result.description,
        result: result.result 
      })
      
      setTimeout(() => {
        setAgentExecution(null)
        setPendingConfirm(null)
      }, 3000)
      
    } catch (error) {
      setAgentExecution({ status: 'failed', error: String(error) })
      setTimeout(() => setAgentExecution(null), 3000)
    }
  }

  // 停止 AI 输出
  const handleStop = () => {
    if (isStreaming) {
      stopStream()
      if (currentStreamingMessageId) {
        const partialContent = streamState.partialContent
        if (partialContent) {
          updateChatMessage(currentStreamingMessageId, {
            content: partialContent + '\n\n（已停止生成）',
            isLoading: false,
          })
          setShowInterruptedBanner(true)
        } else {
          updateChatMessage(currentStreamingMessageId, {
            content: '（已停止生成）',
            isLoading: false,
          })
        }
      }
      setLoading(false)
      setCurrentStreamingMessageId(null)
      message.info('已停止生成')
    } else if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setLoading(false)
      message.info('已停止生成')
    }
  }

  const handleSavePartial = () => {
    const partial = savePartial()
    if (partial) {
      message.success(`已保存 ${partial.content.length} 字符`)
    }
  }

  const handleResumeStream = async () => {
    setShowInterruptedBanner(false)
    await resumeStream()
  }

  const handleDiscardPartial = () => {
    setShowInterruptedBanner(false)
    if (partialResponse?.id) {
      deletePartial(partialResponse.id)
    }
    resetStream()
  }

  const handleSend = async () => {
    if (!inputValue.trim()) return

    if (useCloudAI) {
      if (!cloudAIConfig?.api_key && !cloudAIConfig?.key_id) {
        message.warning('请先配置云端 AI API Key')
        setConfigModalOpen(true)
        return
      }
      await sendCloudMessage()
      return
    }

    if (!selectedModel) {
      message.warning('请选择模型')
      return
    }

    const userMessage: Message = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date().toISOString(),
    }

    addChatMessage(userMessage)
    setInputValue('')
    setLoading(true)

    extractMemory(userMessage.content)

    // 获取最后一条 AI 消息作为上下文
    const lastAssistantMessage = [...messages].reverse().find(m => m.role === 'assistant')
    const agentContext = lastAssistantMessage ? {
      content: lastAssistantMessage.content,
      content_type: 'generated',
    } : undefined

    const agentResult = await executeAgent(userMessage.content, agentContext)
    
    if (agentResult.executed) {
      if (agentResult.result?.need_confirm) {
        setLoading(false)
        return
      }
      
      const assistantMessage: Message = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: formatAgentResult(agentResult.result),
        timestamp: new Date().toISOString(),
      }
      
      addChatMessage(assistantMessage)
      setLoading(false)
      return
    }

    const assistantMessageId = `msg_${Date.now() + 1}`
    addChatMessage({
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isLoading: true,
    })

    try {
      let fullResponse = ''
      let knowledgeSources: KnowledgeSource[] | undefined
      let retrievalInfo: RetrievalInfo | undefined

      abortControllerRef.current = new AbortController()

      if (useKnowledge && selectedCollection) {
        try {
          const chatMessages = messages.map(m => ({
            role: m.role,
            content: m.content
          }))
          chatMessages.push({ role: 'user', content: userMessage.content })

          const response = await fetch(`${API_BASE_URL}/inference/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              model: selectedModel,
              messages: chatMessages,
              options: {
                max_tokens: 1024,
                temperature: 0.7,
                backend: currentBackend,
              },
              knowledge: {
                use_knowledge: true,
                collection_id: selectedCollection,
                auto_retrieve: autoRetrieve,
                top_k: 5,
                include_sources: true
              }
            }),
            signal: abortControllerRef.current.signal
          })

          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
          }

          const data = await response.json()
          fullResponse = data.message?.content || data.text || ''
          knowledgeSources = data.knowledge_sources
          retrievalInfo = data.retrieval_info

          updateChatMessage(assistantMessageId, {
            content: fullResponse,
            isLoading: false,
            knowledge_sources: knowledgeSources,
            retrieval_info: retrievalInfo
          })
        } catch (error) {
          if (error instanceof Error && error.name === 'AbortError') {
            updateChatMessage(assistantMessageId, {
              content: '（已停止生成）',
              isLoading: false
            })
            return
          }
          throw error
        }
      } else {
        const STREAM_TIMEOUT = 120000
        let timeoutId: ReturnType<typeof setTimeout> | null = null
        
        const timeoutPromise = new Promise<never>((_, reject) => {
          timeoutId = setTimeout(() => {
            reject(new Error('请求超时'))
          }, STREAM_TIMEOUT)
        })

        let contextPrompt = ''
        try {
          const memoryResponse = await fetch(`${API_BASE_URL}/memory/recall`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: userMessage.content, top_k: 3 })
          })
          if (memoryResponse.ok) {
            const memoryData = await memoryResponse.json()
            if (memoryData.context) {
              contextPrompt = `\n[用户记忆]\n${memoryData.context}\n\n`
            }
          }
        } catch (e) {
          console.warn('获取记忆上下文失败:', e)
        }

        try {
          await Promise.race([
            streamInference(
              {
                modelId: selectedModel,
                prompt: contextPrompt + buildPrompt(messages, userMessage.content),
                maxTokens: 1024,
                temperature: 0.7,
                backend: currentBackend,
              },
              (text: string) => {
                fullResponse += text
                updateChatMessage(assistantMessageId, {
                  content: fullResponse,
                  isLoading: false
                })
              },
              undefined,
              abortControllerRef.current.signal
            ),
            timeoutPromise
          ])
          
          if (timeoutId) clearTimeout(timeoutId)
        } catch (raceError: unknown) {
          if (timeoutId) clearTimeout(timeoutId)
          throw raceError
        }
      }
      
      if (currentSessionId) {
        await fetch(`${API_BASE_URL}/chat/session/${currentSessionId}/message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [userMessage, { 
              ...userMessage, 
              role: 'assistant', 
              content: fullResponse, 
              id: assistantMessageId,
              knowledge_sources: knowledgeSources,
              retrieval_info: retrievalInfo
            }]
          })
        })
      }
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        updateChatMessage(assistantMessageId, {
          content: '（已停止生成）',
          isLoading: false
        })
        return
      }

      const errorMsg = error instanceof Error ? error.message : '推理失败'
      updateChatMessage(assistantMessageId, {
        content: `错误: ${errorMsg}`,
        isLoading: false
      })
    } finally {
      setLoading(false)
      abortControllerRef.current = null
    }
  }

  // 发送云端 AI 消息
  const sendCloudMessage = async () => {
    if (!cloudAIConfig?.api_key && !cloudAIConfig?.key_id) {
      message.warning('请先配置云端 AI API Key')
      setConfigModalOpen(true)
      return
    }

    const userContent = inputValue.trim()
    if (!userContent) return

    const userMessage: Message = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: userContent,
      timestamp: new Date().toISOString(),
    }

    addChatMessage(userMessage)
    setInputValue('')
    setLoading(true)

    // 提取记忆（云端 AI 也支持）
    extractMemory(userContent)

    // 执行 Agent 操作（云端 AI 也支持）
    const agentResult = await executeAgent(userContent)
    
    if (agentResult.executed) {
      if (agentResult.result?.need_confirm) {
        setLoading(false)
        return
      }
      
      const assistantMessage: Message = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: formatAgentResult(agentResult.result),
        timestamp: new Date().toISOString(),
      }
      
      addChatMessage(assistantMessage)
      setLoading(false)
      return
    }

    // 执行 Skill 操作（云端 AI 也支持）
    const skillResult = await detectAndExecuteSkill(userContent)
    if (skillResult.executed && skillResult.result) {
      const skillMessage: Message = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: `**Skill 执行结果**\n\n\`\`\`json\n${JSON.stringify(skillResult.result.result, null, 2)}\n\`\`\``,
        timestamp: new Date().toISOString(),
      }
      
      addChatMessage(skillMessage)
      setLoading(false)
      return
    }

    const assistantMessageId = `msg_${Date.now() + 1}`
    addChatMessage({
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isLoading: true,
    })

    try {
      let fullResponse = ''

      // 创建 AbortController
      abortControllerRef.current = new AbortController()

      // 构建消息历史（只包含用户和助手消息，过滤掉系统消息和加载中的消息）
      const chatHistory = messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .filter(m => !m.isLoading)
        .map(m => ({ role: m.role, content: m.content }))
      
      // 添加当前用户消息
      chatHistory.push({ role: 'user', content: userContent })

      // 知识库检索（云端 AI 也支持）
      let knowledgeContext = ''
      if (useKnowledge && selectedCollection && autoRetrieve) {
        try {
          const ragResponse = await fetch(`${API_BASE_URL}/knowledge/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              collection_id: selectedCollection,
              query: userContent,
              top_k: 5
            })
          })
          if (ragResponse.ok) {
            const ragData = await ragResponse.json()
            if (ragData.results && ragData.results.length > 0) {
              knowledgeContext = '\n\n[知识库相关信息]\n' + ragData.results.map((r: any) => r.content).join('\n\n')
            }
          }
        } catch (e) {
          console.warn('知识库检索失败:', e)
        }
      }

      // 项目上下文检索（云端 AI 也支持）
      let projectContext = ''
      try {
        const contextResponse = await fetch(`${API_BASE_URL}/context/chat-context`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: userContent,
            max_length: 2000
          })
        })
        if (contextResponse.ok) {
          const contextData = await contextResponse.json()
          if (contextData.has_context && contextData.context) {
            projectContext = '\n\n[项目上下文]\n' + contextData.context
          }
        }
      } catch (e) {
        console.warn('项目上下文检索失败:', e)
      }

      // 如果有知识库上下文或项目上下文，修改最后一条用户消息
      const contextInfo = knowledgeContext + projectContext
      if (contextInfo) {
        // 替换最后一条消息为增强版本（包含上下文）
        chatHistory[chatHistory.length - 1] = {
          role: 'user',
          content: `请参考以下信息回答问题：${contextInfo}\n\n问题：${userContent}`
        }
      }

      console.log('发送云端 AI 请求:', {
        provider: cloudAIConfig.provider,
        key_id: cloudAIConfig.key_id,
        model: selectedCloudModel,
        messageCount: chatHistory.length,
        useKnowledge: useKnowledge && selectedCollection
      })

      // 调用云端 AI 流式接口
      const response = await fetch(`${API_BASE_URL}/cloud/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: cloudAIConfig.provider,
          api_key: cloudAIConfig.api_key,
          key_id: cloudAIConfig.key_id,
          group_id: cloudAIConfig.group_id,
          base_url: cloudAIConfig.base_url,
          model: selectedCloudModel || cloudAIConfig.model || 'MiniMax-M2.5',
          messages: chatHistory,
          stream: true,
        }),
        signal: abortControllerRef.current.signal,
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || '云端 AI 调用失败')
      }

      // 读取流式响应
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader!.read()
        if (done) {
          console.log('流式响应完成')
          break
        }

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              console.log('收到 [DONE] 信号')
              continue
            }

            try {
              const parsed = JSON.parse(data)
              
              // 处理错误
              if (parsed.error) {
                console.error('API 返回错误:', parsed.error)
                throw new Error(parsed.error)
              }
              
              // 处理内容
              if (parsed.content) {
                fullResponse += parsed.content
                updateChatMessage(assistantMessageId, {
                  content: fullResponse,
                  isLoading: false
                })
              }
            } catch (parseError) {
              // 如果是 JSON 解析错误，忽略
              if (parseError instanceof SyntaxError) {
                console.log('JSON 解析错误，跳过:', data.substring(0, 50))
              } else {
                throw parseError
              }
            }
          }
        }
      }

      // 如果没有收到任何响应
      if (!fullResponse) {
        updateChatMessage(assistantMessageId, {
          content: '（云端 AI 未返回任何内容）',
          isLoading: false
        })
      }

    } catch (error: unknown) {
      // 如果是用户主动取消，不显示错误
      if (error instanceof Error && error.name === 'AbortError') {
        updateChatMessage(assistantMessageId, {
          content: '（已停止生成）',
          isLoading: false
        })
        return
      }

      const errorMsg = error instanceof Error ? error.message : '云端 AI 调用失败'
      console.error('云端 AI 调用失败:', errorMsg)
      updateChatMessage(assistantMessageId, {
        content: `错误：${errorMsg}`,
        isLoading: false
      })
      message.error(errorMsg)
    } finally {
      setLoading(false)
      abortControllerRef.current = null
    }
  }

  const buildPrompt = (_history: Message[], _newMessage: string): string => {
    const MAX_CONTEXT_TOKENS = 4000
    const AVG_CHARS_PER_TOKEN = 2
    
    let prompt = ''
    let estimatedTokens = 0
    
    const recentHistory = _history.slice(-20)
    
    for (const msg of recentHistory) {
      const msgTokens = Math.ceil(msg.content.length / AVG_CHARS_PER_TOKEN)
      
      if (estimatedTokens + msgTokens > MAX_CONTEXT_TOKENS) {
        break
      }
      
      if (msg.role === 'user') {
        prompt += `User: ${msg.content}\n`
      } else if (msg.role === 'assistant') {
        prompt += `Assistant: ${msg.content}\n`
      }
      estimatedTokens += msgTokens
    }
    
    prompt += `User: ${_newMessage}\n`
    prompt += `Assistant: `
    return prompt
  }

  // 格式化 Agent 执行结果
  const formatAgentResult = (result: any): string => {
    if (!result) return '操作完成'
    
    if (result.success === false) {
      return `❌ 操作失败：${result.error || '未知错误'}`
    }
    
    const actionMessages: Record<string, (r: any) => string> = {
      file_create: (r) => `✅ 文件已创建：${r.data?.path || '完成'}`,
      file_read: (r) => {
        const content = r.data?.content || ''
        const lines = r.data?.total_lines || 0
        const truncated = r.data?.truncated ? `（共 ${lines} 行，已截断）` : ''
        return `📄 文件内容${truncated}：\n\`\`\`\n${content}\n\`\`\``
      },
      file_write: (_r) => `✅ 文件已更新：${_r.data?.path || '完成'}`,
      file_delete: () => `✅ 文件已删除`,
      file_list: (r) => {
        const files = r.data?.files || []
        const count = r.data?.count || 0
        const fileList = files.map((f: any) => 
          `${f.is_dir ? '📁' : '📄'} ${f.name}${f.is_dir ? '/' : ''}`
        ).join('\n')
        return `📂 找到 ${count} 个项目：\n${fileList}`
      },
      app_open: () => `✅ 应用已打开`,
      url_open: () => `✅ 网页已打开`,
    }
    
    const action = result.data?.action || ''
    const formatter = actionMessages[action]
    
    if (formatter) {
      return formatter(result)
    }
    
    return `✅ 操作完成：${result.message || '成功'}`
  }

  const handleRetry = async (messageId: string) => {
    const msgIndex = messages.findIndex(m => m.id === messageId)
    if (msgIndex === -1 || !selectedModel) return

    const userMessage = messages[msgIndex - 1]
    if (!userMessage || userMessage.role !== 'user') return

    setChatMessages(messages.filter((_, i) => i <= msgIndex - 1))
    setInputValue(userMessage.content)
    setLoading(true)

    const assistantMessageId = `msg_${Date.now()}`
    addChatMessage({
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isLoading: true,
    })

    try {
      let fullResponse = ''

      abortControllerRef.current = new AbortController()

      await streamInference(
        {
          modelId: selectedModel,
          prompt: buildPrompt(messages.slice(0, msgIndex - 1), userMessage.content),
          maxTokens: 1024,
          temperature: 0.7,
          backend: currentBackend,
        },
        (text: string) => {
          fullResponse += text
          updateChatMessage(assistantMessageId, {
            content: fullResponse,
            isLoading: false
          })
        },
        undefined,
        abortControllerRef.current.signal
      )
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        updateChatMessage(assistantMessageId, {
          content: '（已停止生成）',
          isLoading: false
        })
        return
      }

      const errorMsg = error instanceof Error ? error.message : '推理失败'
      updateChatMessage(assistantMessageId, {
        content: `错误: ${errorMsg}`,
        isLoading: false
      })
    } finally {
      setLoading(false)
      abortControllerRef.current = null
    }
  }

  const handleDelete = (messageId: string) => {
    setChatMessages(messages.filter(m => m.id !== messageId))
  }

  const modelOptions = currentBackend === 'ollama'
    ? ollamaModels.map(m => ({ value: m.id, label: m.name }))
    : hfModels.map(m => ({ value: m.id, label: m.name }))

  const currentBackendInfo = backends.find(b => b.id === currentBackend)
  const isBackendAvailable = currentBackendInfo?.available ?? true

  const getSessionTitle = () => {
    if (messages.length === 0) return '新对话'
    const firstMsg = messages.find(m => m.role === 'user')
    return firstMsg?.content.slice(0, 20) || '新对话'
  }

  const exportChat = (format: 'markdown' | 'json') => {
    if (messages.length === 0) {
      message.warning('暂无对话内容')
      return
    }

    if (format === 'markdown') {
      let content = `# ${getSessionTitle()}\n\n`
      content += `导出时间: ${new Date().toLocaleString('zh-CN')}\n\n`
      content += `---\n\n`

      for (const msg of messages) {
        const role = msg.role === 'user' ? '👤 用户' : '🤖 助手'
        content += `## ${role}\n\n${msg.content}\n\n`
      }

      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${getSessionTitle()}_${Date.now()}.md`
      a.click()
      URL.revokeObjectURL(url)
      message.success('已导出为 Markdown')
    } else if (format === 'json') {
      const data = {
        title: getSessionTitle(),
        exportedAt: new Date().toISOString(),
        messages: messages
      }
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${getSessionTitle()}_${Date.now()}.json`
      a.click()
      URL.revokeObjectURL(url)
      message.success('已导出为 JSON')
    }
  }

  const clearChat = () => {
    Modal.confirm({
      title: '确认清空',
      content: '确定要清空当前对话吗？',
      okText: '清空',
      okButtonProps: { danger: true },
      onOk: () => {
        clearChatSession()
        message.success('对话已清空')
      }
    })
  }

  return (
    <motion.div
      className="chat-container"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transitions.slower}
      style={{
        height: 'calc(100vh - 72px)',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--bg-primary)',
      }}
    >
      <motion.div
        className="chat-toolbar"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, ...transitions.base }}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 24px',
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-color)',
          flexShrink: 0,
        }}
      >
        <Space>
          <motion.div
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={createNewSession}
              style={{ borderRadius: '8px', height: 36 }}
            >
              新对话
            </Button>
          </motion.div>
          <motion.div
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Button
              icon={<HistoryOutlined />}
              onClick={() => setHistoryOpen(true)}
              style={{ borderRadius: '8px', height: 36 }}
            >
              历史
            </Button>
          </motion.div>
          <motion.div
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Button
              icon={<BulbOutlined />}
              onClick={() => setMemoryManagerOpen(true)}
              style={{ borderRadius: '8px', height: 36 }}
            >
              记忆
            </Button>
          </motion.div>
          <Tooltip title={!cloudAIConfig?.api_key && !cloudAIConfig?.key_id ? '点击配置云端 AI' : useCloudAI ? '当前使用云端 AI' : '切换到云端 AI'}>
            <motion.div
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Button
                icon={<CloudOutlined />}
                onClick={() => {
                  if (!cloudAIConfig?.api_key && !cloudAIConfig?.key_id) {
                    setConfigModalOpen(true)
                  } else if (!useCloudAI) {
                    setUseCloudAI(true)
                  } else {
                    setUseCloudAI(false)
                  }
              }}
              type={useCloudAI ? 'primary' : 'default'}
              style={{ borderRadius: '8px', height: 36 }}
            >
              {useCloudAI ? '☁️ 云端' : '🤖 本地'}
              </Button>
            </motion.div>
          </Tooltip>
          <Tooltip title={collections.length === 0 ? '请先在知识库页面上传文档' : '启用知识库检索'}>
            <motion.div
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Button
                icon={<BookOutlined />}
                onClick={() => setUseKnowledge(!useKnowledge)}
                type={useKnowledge ? 'primary' : 'default'}
                style={{ borderRadius: '8px', height: 36 }}
                disabled={collections.length === 0}
              >
                知识库
              </Button>
            </motion.div>
          </Tooltip>
        </Space>

        <Space>
          <Tooltip title={theme === 'light' ? '切换到深色模式' : '切换到浅色模式'}>
            <motion.div
              whileHover={{ scale: 1.05, rotate: 15 }}
              whileTap={{ scale: 0.95 }}
            >
              <Button
                icon={theme === 'light' ? <MoonOutlined /> : <SunOutlined />}
                onClick={toggleTheme}
                style={{ borderRadius: '8px', height: 36 }}
              />
            </motion.div>
          </Tooltip>
          <Select
            value={currentBackend}
            onChange={handleBackendChange}
            style={{ width: 130, borderRadius: '8px' }}
            options={backends.map(b => ({
              value: b.id,
              label: b.available ? b.name : `${b.name} (不可用)`,
              disabled: !b.available
            }))}
          />
          <Select
            placeholder={currentBackend === 'ollama' ? "选择 Ollama 模型" : "选择模型"}
            value={selectedModel}
            onChange={setSelectedModel}
            style={{ width: 180, borderRadius: '8px' }}
            options={modelOptions}
            disabled={loading}
            loading={modelOptions.length === 0}
            suffixIcon={<Badge status={isBackendAvailable ? 'success' : 'error'} />}
          />
          <Dropdown
            menu={{
              items: [
                { key: 'md', label: '导出 Markdown', icon: <ExportOutlined />, onClick: () => exportChat('markdown') },
                { key: 'json', label: '导出 JSON', icon: <ExportOutlined />, onClick: () => exportChat('json') },
                { type: 'divider' },
                { key: 'clear', label: '清空对话', icon: <ClearOutlined />, danger: true, onClick: clearChat },
              ]
            }}
          >
            <motion.div
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Button icon={<MoreOutlined />} style={{ borderRadius: '8px', height: 36 }} />
            </motion.div>
          </Dropdown>
        </Space>
      </motion.div>

      <AnimatePresence>
        {agentExecution && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={transitions.base}
            style={{
              padding: '8px 24px',
              background: 'var(--bg-secondary)',
              borderBottom: '1px solid var(--border-color)',
              overflow: 'hidden',
            }}
          >
          <Alert
            message={
              <Space>
                {agentExecution.status === 'executing' && <LoadingOutlined spin />}
                {agentExecution.status === 'completed' && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                {agentExecution.status === 'failed' && <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                {agentExecution.status === 'confirm' && <ThunderboltFilled style={{ color: '#faad14' }} />}
                <span>
                  {agentExecution.status === 'executing' && '正在执行操作...'}
                  {agentExecution.status === 'completed' && `✅ ${agentExecution.description || '操作完成'}`}
                  {agentExecution.status === 'failed' && `❌ 执行失败：${agentExecution.error}`}
                  {agentExecution.status === 'confirm' && `⚠️ 确认执行：${agentExecution.description}`}
                </span>
              </Space>
            }
            type={
              agentExecution.status === 'failed' ? 'error' :
              agentExecution.status === 'completed' ? 'success' :
              agentExecution.status === 'confirm' ? 'warning' : 'info'
            }
            showIcon
            style={{ borderRadius: '8px', maxWidth: 768, margin: '0 auto' }}
            action={
              agentExecution.status === 'confirm' && (
                <Space>
                  <Button size="small" onClick={() => { setAgentExecution(null); setPendingConfirm(null) }}>
                    取消
                  </Button>
                  <Button size="small" type="primary" danger onClick={confirmDangerousAction}>
                    确认执行
                  </Button>
                </Space>
              )
            }
          />
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        className="chat-messages-area"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2, ...transitions.base }}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '24px 24px 0',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div style={{
          maxWidth: 768,
          width: '100%',
          margin: '0 auto',
          flex: 1,
        }}>
          <AnimatePresence>
            {isStreaming && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                style={{ marginBottom: 16 }}
              >
                <ConnectionStatus state={streamState} showStats />
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {showInterruptedBanner && partialResponse && (
              <InterruptedContentBanner
                content={partialResponse.content}
                onContinue={handleResumeStream}
                onSave={() => {
                  handleSavePartial()
                  setShowInterruptedBanner(false)
                }}
                onDiscard={handleDiscardPartial}
              />
            )}
          </AnimatePresence>

          {messages.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={transitions.spring}
              style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-tertiary)',
                padding: '40px 20px',
              }}
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, ...transitions.spring }}
                style={{
                  width: 80,
                  height: 80,
                  borderRadius: '50%',
                  background: 'var(--gradient-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '40px',
                  color: '#fff',
                  marginBottom: 24,
                  boxShadow: '0 8px 30px rgba(59, 130, 246, 0.3)',
                }}
              >
                <RobotOutlined />
              </motion.div>
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, ...transitions.base }}
              >
                <Title level={4} style={{ margin: '0 0 8px', color: 'var(--text-primary)' }}>
                  开始新的对话
                </Title>
              </motion.div>
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4, ...transitions.base }}
              >
                <Text style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>
                  选择模型后，输入您的问题开始对话
                </Text>
              </motion.div>
              {!selectedModel && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.5, ...transitions.base }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Button
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    onClick={() => textareaRef.current?.focus()}
                    style={{ marginTop: 24, borderRadius: '8px', height: 40 }}
                  >
                    选择模型开始
                  </Button>
                </motion.div>
              )}
            </motion.div>
          ) : (
            <div>
              {enableVirtualScroll ? (
                <Virtuoso
                  data={messages}
                  itemContent={(index, msg) => (
                    <ChatMessage
                      key={msg.id}
                      role={msg.role as 'user' | 'assistant'}
                      content={msg.content}
                      timestamp={msg.timestamp}
                      isLoading={msg.isLoading}
                      isStreaming={loading && index === messages.length - 1 && msg.role === 'assistant'}
                      enableTypewriter={true}
                      typewriterSpeed={50}
                      onRetry={msg.role === 'assistant' ? () => handleRetry(msg.id) : undefined}
                      onDelete={() => handleDelete(msg.id)}
                      knowledge_sources={msg.knowledge_sources}
                      retrieval_info={msg.retrieval_info}
                    />
                  )}
                  followOutput="smooth"
                  style={{ height: 'calc(100vh - 280px)' }}
                  alignToBottom
                />
              ) : (
                <>
                  {messages.map((msg) => (
                    <ChatMessage
                      key={msg.id}
                      role={msg.role as 'user' | 'assistant'}
                      content={msg.content}
                      timestamp={msg.timestamp}
                      isLoading={msg.isLoading}
                      isStreaming={loading && msg.id === messages[messages.length - 1]?.id && msg.role === 'assistant'}
                      enableTypewriter={true}
                      typewriterSpeed={50}
                      onRetry={msg.role === 'assistant' ? () => handleRetry(msg.id) : undefined}
                      onDelete={() => handleDelete(msg.id)}
                      knowledge_sources={msg.knowledge_sources}
                      retrieval_info={msg.retrieval_info}
                    />
                  ))}
                  <div ref={messagesEndRef} />
                </>
              )}
            </div>
          )}
        </div>
      </motion.div>

      <motion.div
        className="chat-input-area"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, ...transitions.base }}
        style={{
          padding: '16px 24px 24px',
          background: 'var(--bg-primary)',
          borderTop: '1px solid var(--border-color)',
          flexShrink: 0,
        }}
      >
        <div style={{
          maxWidth: 768,
          margin: '0 auto',
        }}>
          <AnimatePresence>
            {(useKnowledge || useCloudAI) && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={transitions.base}
                style={{
                  marginBottom: 12,
                  display: 'flex',
                  gap: 12,
                  flexWrap: 'wrap',
                  overflow: 'hidden',
                }}
              >
                {useKnowledge && collections.length > 0 && (
                  <Select
                    placeholder="选择知识库"
                    value={selectedCollection}
                    onChange={setSelectedCollection}
                    style={{ width: 200, borderRadius: '8px' }}
                    options={collections.map(c => ({
                      value: c.id,
                      label: `${c.name} (${c.count} 条)`
                    }))}
                    disabled={loading}
                    size="small"
                  />
                )}
                {useKnowledge && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Text style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>自动检索</Text>
                    <Switch
                      size="small"
                      checked={autoRetrieve}
                      onChange={setAutoRetrieve}
                    />
                  </div>
                )}
                {useCloudAI && cloudModels.length > 0 && (
                  <Select
                    value={selectedCloudModel}
                    onChange={setSelectedCloudModel}
                    style={{ width: 220, borderRadius: '8px' }}
                    options={cloudModels}
                    disabled={loading}
                    size="small"
                  />
                )}
              </motion.div>
            )}
          </AnimatePresence>

          <motion.div
            whileFocus={{ scale: 1.005 }}
            style={{
              background: 'var(--bg-secondary)',
              borderRadius: '12px',
              border: '1px solid var(--border-color)',
              padding: '12px 16px',
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.04)',
              transition: 'all 0.3s ease',
            }}
          >
            <TextArea
              ref={textareaRef}
              placeholder={selectedModel ? "输入你的问题... (Shift+Enter 换行)" : "请先选择模型"}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              autoSize={{ minRows: 1, maxRows: 6 }}
              disabled={loading || !selectedModel}
              aria-label="消息输入框"
              aria-describedby="input-hint"
              tabIndex={0}
              style={{
                resize: 'none',
                border: 'none',
                background: 'transparent',
                fontSize: '15px',
                lineHeight: 1.6,
                boxShadow: 'none',
                padding: 0,
              }}
            />
            <span id="input-hint" className="sr-only" style={{ position: 'absolute', width: 1, height: 1, padding: 0, margin: -1, overflow: 'hidden', clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0 }}>
              按 Enter 发送消息，Shift+Enter 换行
            </span>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: 12,
              paddingTop: 12,
              borderTop: '1px solid var(--border-color)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {selectedModel ? (
                  <>
                    <Avatar
                      size="small"
                      icon={<RobotOutlined />}
                      style={{ background: 'var(--gradient-primary)', width: 24, height: 24 }}
                    />
                    <Text type="secondary" style={{ fontSize: '13px' }}>
                      {selectedModel}
                    </Text>
                  </>
                ) : (
                  <Text type="secondary" style={{ fontSize: '13px' }}>
                    请先选择模型
                  </Text>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {loading ? (
                  <>
                    <StreamingIndicator
                      isActive={isStreaming}
                      contentLength={streamState.partialContent.length}
                      speed={getStats().chunksPerSecond * 10}
                    />
                    <StopButton
                      onStop={handleStop}
                      onSavePartial={handleSavePartial}
                      hasPartialContent={streamState.partialContent.length > 0}
                      partialContentLength={streamState.partialContent.length}
                      variant="default"
                    />
                  </>
                ) : (
                  <motion.div
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <Button
                      type="primary"
                      icon={<SendOutlined />}
                      onClick={handleSend}
                      disabled={!selectedModel || !inputValue.trim()}
                      aria-label="发送消息"
                      aria-disabled={!selectedModel || !inputValue.trim()}
                      style={{
                        borderRadius: '8px',
                        height: 36,
                        padding: '0 20px',
                        fontSize: '14px',
                        fontWeight: 500,
                      }}
                    >
                      发送
                    </Button>
                  </motion.div>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      </motion.div>

      <ChatHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        sessions={sessions}
        onLoadSession={loadSession}
        onDeleteSession={deleteSession}
      />

      {/* 记忆管理弹窗 */}
      <MemoryManager
        open={memoryManagerOpen}
        onClose={() => setMemoryManagerOpen(false)}
      />

      {/* 记忆提示 */}
      <AnimatePresence>
        {memoryHint.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            transition={transitions.spring}
            style={{ position: 'fixed', bottom: 120, right: 24, maxWidth: 400, zIndex: 1000 }}
          >
            <Alert
              type="info"
              message="💡 AI 记住了这些信息"
              description={
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {memoryHint.map((h, i) => <li key={i}>{h}</li>)}
                </ul>
              }
              closable
              onClose={() => setMemoryHint([])}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* 云端 AI 配置弹窗 */}
      <Modal
        open={configModalOpen}
        onCancel={() => setConfigModalOpen(false)}
        footer={null}
        width={600}
      >
        <APIKeyManager
          onConfigChange={(config: APIKeyConfig) => {
            console.log('配置已更新:', config)
            
            // 保存配置到本地存储（用于下次加载时恢复）
            setCloudAIConfig(config)
            if (config.api_key || config.key_id) {
              setUseCloudAI(true)
            }
            if (config.provider) {
              loadCloudModels(config.provider)
              if (config.model) {
                setSelectedCloudModel(config.model)
              }
            }
          }}
          initialConfig={cloudAIConfig}
        />
      </Modal>

      {/* 部分保存指示器 */}
      <PartialSaveIndicator
        saved={lastPartialSave?.saved || false}
        content={lastPartialSave?.content || ''}
        timestamp={lastPartialSave?.timestamp || 0}
      />

      <style>{`
        .chat-container {
          position: relative;
        }
        
        .chat-messages-area::-webkit-scrollbar {
          width: 6px;
        }

        .chat-messages-area::-webkit-scrollbar-track {
          background: transparent;
        }

        .chat-messages-area::-webkit-scrollbar-thumb {
          background: var(--border-color);
          border-radius: 3px;
        }

        .chat-messages-area::-webkit-scrollbar-thumb:hover {
          background: var(--text-tertiary);
        }

        .chat-toolbar {
          transition: all 0.3s ease;
        }

        .chat-input-area {
          transition: all 0.3s ease;
        }
        
        .chat-input-area:focus-within {
          box-shadow: 0 -2px 12px rgba(59, 130, 246, 0.1);
        }
        
        /* 响应式布局 */
        @media (max-width: 768px) {
          .chat-toolbar {
            padding: 8px 12px !important;
            flex-wrap: wrap;
            gap: 8px;
          }
          
          .chat-toolbar .ant-space {
            flex-wrap: wrap;
          }
          
          .chat-toolbar .ant-btn {
            height: 32px !important;
            padding: 0 8px !important;
            font-size: 13px !important;
          }
          
          .chat-messages-area {
            padding: 16px 12px 0 !important;
          }
          
          .chat-input-area {
            padding: 12px 12px 16px !important;
          }
          
          .chat-input-area .ant-select {
            width: 100% !important;
          }
        }
        
        @media (max-width: 480px) {
          .chat-toolbar .ant-btn span:not(.anticon) {
            display: none;
          }
          
          .chat-toolbar .ant-select {
            width: 100px !important;
          }
          
          .chat-input-area .ant-btn {
            padding: 0 12px !important;
          }
        }
      `}</style>
    </motion.div>
  )
}