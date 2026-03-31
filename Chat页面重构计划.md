# AI 对话页面重构计划

## 问题诊断

### 一、代码结构问题

| 问题 | 现状 | 影响 |
|------|------|------|
| **代码臃肿** | Chat.tsx 有 2160 行 | 难以维护、难以测试 |
| **职责过多** | 一个组件处理所有功能 | 修改风险高 |
| **状态管理混乱** | 20+ useState | 状态追踪困难 |
| **没有自定义 Hooks** | 所有逻辑在组件内 | 无法复用 |

### 二、功能实现问题

#### 1. 流式响应处理
```tsx
// 当前问题：云端 AI 流式处理不完整
// 第 1067-1116 行
while (true) {
  const { done, value } = await reader!.read()
  // 问题：没有错误恢复机制
  // 问题：没有重连逻辑
  // 问题：没有超时处理
}
```

#### 2. Agent 执行状态
```tsx
// 当前问题：状态管理混乱
const [agentExecution, setAgentExecution] = useState<AgentExecution | null>(null)
const [pendingConfirm, setPendingConfirm] = useState<{...} | null>(null)
// 问题：两个状态分离，同步困难
// 问题：没有执行队列
// 问题：没有执行历史
```

#### 3. 知识库集成
```tsx
// 当前问题：知识库检索是独立的，没有和对话流程整合
if (useKnowledge && selectedCollection && autoRetrieve) {
  // 问题：检索结果没有上下文融合
  // 问题：没有检索结果展示
  // 问题：没有检索反馈机制
}
```

#### 4. 记忆系统
```tsx
// 当前问题：只是简单调用，没有智能应用
const extractMemory = async (content: string) => {
  // 问题：没有记忆检索优化
  // 问题：没有记忆优先级
  // 问题：没有记忆遗忘机制
}
```

### 三、用户体验问题

| 功能 | 状态 | 优先级 |
|------|------|--------|
| 消息编辑 | ❌ 未实现 | P0 |
| 消息复制 | ❌ 未实现 | P0 |
| 消息引用/回复 | ❌ 未实现 | P1 |
| 输入建议 | ❌ 未实现 | P1 |
| 快捷操作 | ❌ 未实现 | P1 |
| 消息搜索 | ❌ 未实现 | P2 |
| 消息标签 | ❌ 未实现 | P2 |
| 对话分支 | ❌ 未实现 | P2 |
| 多模态输入 | ❌ 未实现 | P2 |

### 四、性能问题

| 问题 | 现状 | 影响 |
|------|------|------|
| 消息列表渲染 | 直接 map 渲染 | 消息多时卡顿 |
| 虚拟滚动 | 仅在 >100 条时启用 | 应该默认启用 |
| 状态更新 | 整体更新 | 不必要的重渲染 |
| 防抖节流 | 仅消息保存有 | 输入、滚动等缺失 |

---

## 重构方案

### 一、架构设计

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Chat 页面新架构                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Chat.tsx (主容器，~200 行)                                              │
│  ├── ChatHeader.tsx          # 顶部工具栏                               │
│  ├── ChatMessageList.tsx     # 消息列表（虚拟滚动）                      │
│  │   └── ChatMessage.tsx     # 单条消息                                 │
│  │       ├── MessageContent.tsx    # 消息内容渲染                       │
│  │       ├── MessageActions.tsx    # 消息操作按钮                       │
│  │       └── MessageSources.tsx    # 知识来源展示                       │
│  ├── ChatInput.tsx           # 输入区域                                 │
│  │   ├── InputSuggestions.tsx      # 输入建议                          │
│  │   └── AttachmentUpload.tsx      # 附件上传                          │
│  ├── AgentStatus.tsx         # Agent 执行状态                           │
│  └── SidePanels/                                                      │
│      ├── HistoryPanel.tsx    # 历史记录                                 │
│      ├── MemoryPanel.tsx     # 记忆管理                                 │
│      └── SettingsPanel.tsx   # 对话设置                                 │
│                                                                         │
│  Hooks/                                                                │
│  ├── useChatMessages.ts      # 消息管理                                 │
│  ├── useChatStream.ts        # 流式响应                                 │
│  ├── useAgentExecutor.ts     # Agent 执行                               │
│  ├── useKnowledgeRetrieval.ts # 知识检索                                │
│  ├── useMemorySystem.ts      # 记忆系统                                 │
│  └── useChatSession.ts       # 会话管理                                 │
│                                                                         │
│  Store/                                                                │
│  └── chatStore.ts            # Zustand 状态管理                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 二、核心模块拆分

#### 1. 状态管理 (chatStore.ts)

```typescript
// 使用 Zustand 统一管理状态
interface ChatStore {
  // 会话状态
  currentSessionId: string | null
  sessions: ChatSession[]
  
  // 消息状态
  messages: Message[]
  streamingMessageId: string | null
  
  // Agent 状态
  agentExecution: AgentExecution | null
  executionQueue: ExecutionTask[]
  
  // UI 状态
  isStreaming: boolean
  isLoading: boolean
  error: string | null
  
  // 设置
  settings: ChatSettings
  
  // Actions
  sendMessage: (content: string) => Promise<void>
  stopStreaming: () => void
  editMessage: (id: string, content: string) => void
  deleteMessage: (id: string) => void
  // ...
}
```

#### 2. 流式响应 Hook (useChatStream.ts)

```typescript
export function useChatStream() {
  const [state, setState] = useState<StreamState>({
    status: 'idle',
    content: '',
    error: null,
  })
  
  const abortControllerRef = useRef<AbortController | null>(null)
  
  const startStream = useCallback(async (request: ChatRequest) => {
    // 完整的流式处理逻辑
    // - 自动重连
    // - 错误恢复
    // - 超时处理
    // - 进度追踪
  }, [])
  
  const stopStream = useCallback(() => {
    // 优雅停止
  }, [])
  
  return { state, startStream, stopStream }
}
```

#### 3. Agent 执行 Hook (useAgentExecutor.ts)

```typescript
export function useAgentExecutor() {
  const [executions, setExecutions] = useState<Execution[]>([])
  const [queue, setQueue] = useState<ExecutionTask[]>([])
  
  const execute = useCallback(async (task: ExecutionTask) => {
    // 执行 Agent 任务
    // - 队列管理
    // - 状态追踪
    // - 错误处理
    // - 确认流程
  }, [])
  
  const confirm = useCallback(async (executionId: string) => {
    // 确认危险操作
  }, [])
  
  return { executions, queue, execute, confirm }
}
```

### 三、功能实现计划

#### 阶段一：核心重构 (P0)

| 任务 | 文件 | 工时 | 说明 |
|------|------|------|------|
| 创建 Zustand Store | `chatStore.ts` | 4h | 统一状态管理 |
| 拆分消息管理 | `useChatMessages.ts` | 4h | 消息 CRUD |
| 拆分流式响应 | `useChatStream.ts` | 6h | 完整流式处理 |
| 拆分 Agent 执行 | `useAgentExecutor.ts` | 4h | Agent 状态管理 |
| 重构 Chat.tsx | `Chat.tsx` | 8h | 主容器简化 |

#### 阶段二：用户体验 (P1)

| 任务 | 文件 | 工时 | 说明 |
|------|------|------|------|
| 消息编辑功能 | `ChatMessage.tsx` | 3h | 编辑已发送消息 |
| 消息复制功能 | `ChatMessage.tsx` | 1h | 一键复制 |
| 消息引用功能 | `ChatMessage.tsx` | 3h | 引用回复 |
| 输入建议 | `InputSuggestions.tsx` | 4h | 智能建议 |
| 快捷操作 | `QuickActions.tsx` | 3h | 常用操作按钮 |

#### 阶段三：高级功能 (P2)

| 任务 | 文件 | 工时 | 说明 |
|------|------|------|------|
| 消息搜索 | `MessageSearch.tsx` | 4h | 搜索历史消息 |
| 对话分支 | `ChatBranch.tsx` | 6h | 分支对话 |
| 多模态输入 | `MultimodalInput.tsx` | 8h | 图片、文件上传 |
| 消息标签 | `MessageTags.tsx` | 3h | 标签分类 |

---

## 详细实现

### 一、chatStore.ts 实现

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  isLoading?: boolean
  isEdited?: boolean
  parentId?: string
  knowledge_sources?: KnowledgeSource[]
  retrieval_info?: RetrievalInfo
}

interface ChatSession {
  id: string
  title: string
  modelId: string
  backend: string
  createdAt: string
  updatedAt: string
}

interface AgentExecution {
  id: string
  status: 'pending' | 'executing' | 'confirming' | 'completed' | 'failed'
  action: string
  description: string
  result?: any
  error?: string
  timestamp: string
}

interface ChatSettings {
  modelId: string
  backend: 'ollama' | 'huggingface' | 'cloud'
  useKnowledge: boolean
  knowledgeCollection?: string
  useMemory: boolean
  temperature: number
  maxTokens: number
}

interface ChatStore {
  // State
  currentSessionId: string | null
  sessions: ChatSession[]
  messages: Message[]
  streamingMessageId: string | null
  streamingContent: string
  agentExecution: AgentExecution | null
  isStreaming: boolean
  isLoading: boolean
  error: string | null
  settings: ChatSettings
  
  // Session Actions
  createSession: (title?: string) => Promise<ChatSession>
  loadSession: (sessionId: string) => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>
  setCurrentSession: (sessionId: string | null) => void
  
  // Message Actions
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => string
  updateMessage: (id: string, updates: Partial<Message>) => void
  deleteMessage: (id: string) => void
  editMessage: (id: string, content: string) => void
  clearMessages: () => void
  
  // Streaming Actions
  startStreaming: (messageId: string) => void
  updateStreamingContent: (content: string) => void
  stopStreaming: () => void
  completeStreaming: () => void
  
  // Agent Actions
  setAgentExecution: (execution: AgentExecution | null) => void
  confirmAgentExecution: () => Promise<void>
  cancelAgentExecution: () => void
  
  // Settings Actions
  updateSettings: (settings: Partial<ChatSettings>) => void
  
  // Error Actions
  setError: (error: string | null) => void
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      // Initial State
      currentSessionId: null,
      sessions: [],
      messages: [],
      streamingMessageId: null,
      streamingContent: '',
      agentExecution: null,
      isStreaming: false,
      isLoading: false,
      error: null,
      settings: {
        modelId: '',
        backend: 'ollama',
        useKnowledge: false,
        useMemory: true,
        temperature: 0.7,
        maxTokens: 2048,
      },
      
      // Session Actions
      createSession: async (title = '新对话') => {
        const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title }),
        })
        const session = await response.json()
        set((state) => ({
          sessions: [session, ...state.sessions],
          currentSessionId: session.id,
          messages: [],
        }))
        return session
      },
      
      loadSession: async (sessionId) => {
        const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`)
        const data = await response.json()
        set({
          currentSessionId: sessionId,
          messages: data.messages || [],
        })
      },
      
      deleteSession: async (sessionId) => {
        await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`, { method: 'DELETE' })
        set((state) => ({
          sessions: state.sessions.filter((s) => s.id !== sessionId),
          currentSessionId: state.currentSessionId === sessionId ? null : state.currentSessionId,
          messages: state.currentSessionId === sessionId ? [] : state.messages,
        }))
      },
      
      setCurrentSession: (sessionId) => {
        set({ currentSessionId: sessionId })
      },
      
      // Message Actions
      addMessage: (message) => {
        const id = `msg_${Date.now()}`
        const newMessage: Message = {
          ...message,
          id,
          timestamp: new Date().toISOString(),
        }
        set((state) => ({
          messages: [...state.messages, newMessage],
        }))
        return id
      },
      
      updateMessage: (id, updates) => {
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, ...updates } : m
          ),
        }))
      },
      
      deleteMessage: (id) => {
        set((state) => ({
          messages: state.messages.filter((m) => m.id !== id),
        }))
      },
      
      editMessage: (id, content) => {
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, content, isEdited: true } : m
          ),
        }))
      },
      
      clearMessages: () => {
        set({ messages: [] })
      },
      
      // Streaming Actions
      startStreaming: (messageId) => {
        set({
          streamingMessageId: messageId,
          streamingContent: '',
          isStreaming: true,
        })
      },
      
      updateStreamingContent: (content) => {
        set({ streamingContent: content })
        const { streamingMessageId } = get()
        if (streamingMessageId) {
          get().updateMessage(streamingMessageId, { content })
        }
      },
      
      stopStreaming: () => {
        set({
          isStreaming: false,
          streamingMessageId: null,
        })
      },
      
      completeStreaming: () => {
        const { streamingMessageId } = get()
        if (streamingMessageId) {
          get().updateMessage(streamingMessageId, { isLoading: false })
        }
        set({
          isStreaming: false,
          streamingMessageId: null,
        })
      },
      
      // Agent Actions
      setAgentExecution: (execution) => {
        set({ agentExecution: execution })
      },
      
      confirmAgentExecution: async () => {
        const { agentExecution } = get()
        if (!agentExecution) return
        
        set({
          agentExecution: { ...agentExecution, status: 'executing' },
        })
        
        try {
          const result = await chatExecuteAgent(agentExecution.action, true)
          set({
            agentExecution: {
              ...agentExecution,
              status: 'completed',
              result: result.result,
            },
          })
        } catch (error) {
          set({
            agentExecution: {
              ...agentExecution,
              status: 'failed',
              error: String(error),
            },
          })
        }
      },
      
      cancelAgentExecution: () => {
        set({ agentExecution: null })
      },
      
      // Settings Actions
      updateSettings: (newSettings) => {
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        }))
      },
      
      // Error Actions
      setError: (error) => {
        set({ error })
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        currentSessionId: state.currentSessionId,
        settings: state.settings,
      }),
    }
  )
)
```

### 二、useChatStream.ts 实现

```typescript
import { useState, useCallback, useRef, useEffect } from 'react'
import { useChatStore } from './chatStore'
import { API_BASE_URL } from '../services/api'

interface StreamState {
  status: 'idle' | 'connecting' | 'streaming' | 'completed' | 'error' | 'stopped'
  content: string
  error: string | null
  chunksReceived: number
  startTime: number | null
  bytesReceived: number
}

interface StreamOptions {
  maxRetries?: number
  retryDelay?: number
  timeout?: number
  onChunk?: (chunk: string, fullContent: string) => void
  onComplete?: (content: string) => void
  onError?: (error: string) => void
}

export function useChatStream(options: StreamOptions = {}) {
  const {
    maxRetries = 3,
    retryDelay = 1000,
    timeout = 60000,
    onChunk,
    onComplete,
    onError,
  } = options

  const [state, setState] = useState<StreamState>({
    status: 'idle',
    content: '',
    error: null,
    chunksReceived: 0,
    startTime: null,
    bytesReceived: 0,
  })

  const abortControllerRef = useRef<AbortController | null>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const retryCountRef = useRef(0)

  const { 
    addMessage, 
    startStreaming, 
    updateStreamingContent, 
    stopStreaming, 
    completeStreaming,
    settings,
    messages,
    currentSessionId,
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
      }
    }, timeout)
  }, [timeout, clearTimeouts])

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim()) return

    const userMessageId = addMessage({
      role: 'user',
      content: content.trim(),
    })

    const assistantMessageId = addMessage({
      role: 'assistant',
      content: '',
      isLoading: true,
    })

    startStreaming(assistantMessageId)

    setState({
      status: 'connecting',
      content: '',
      error: null,
      chunksReceived: 0,
      startTime: Date.now(),
      bytesReceived: 0,
    })

    abortControllerRef.current = new AbortController()
    startTimeout()

    try {
      const chatHistory = messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .filter((m) => !m.isLoading)
        .map((m) => ({ role: m.role, content: m.content }))

      chatHistory.push({ role: 'user', content: content.trim() })

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
            enabled: settings.useMemory,
            auto_extract: true,
            auto_retrieve: true,
            top_k: 3,
          },
          knowledge: {
            use_knowledge: settings.useKnowledge && !!settings.knowledgeCollection,
            collection_id: settings.knowledgeCollection,
            auto_retrieve: true,
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
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      const fullContent = data.message?.content || data.text || ''

      setState((prev) => ({
        ...prev,
        status: 'completed',
        content: fullContent,
      }))

      updateStreamingContent(fullContent)
      completeStreaming()

      if (onComplete) {
        onComplete(fullContent)
      }

      retryCountRef.current = 0

    } catch (error: any) {
      if (error.name === 'AbortError') {
        setState((prev) => ({
          ...prev,
          status: 'stopped',
        }))
        stopStreaming()
        return
      }

      const errorMsg = error.message || '请求失败'
      setState((prev) => ({
        ...prev,
        status: 'error',
        error: errorMsg,
      }))

      if (retryCountRef.current < maxRetries) {
        retryCountRef.current++
        setTimeout(() => {
          sendMessage(content)
        }, retryDelay * retryCountRef.current)
        return
      }

      if (onError) {
        onError(errorMsg)
      }

      completeStreaming()
    } finally {
      clearTimeouts()
      abortControllerRef.current = null
    }
  }, [
    addMessage,
    startStreaming,
    updateStreamingContent,
    completeStreaming,
    stopStreaming,
    settings,
    messages,
    currentSessionId,
    maxRetries,
    retryDelay,
    startTimeout,
    clearTimeouts,
    onComplete,
    onError,
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
  }, [stopStreaming, clearTimeouts])

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
    stop,
    retry,
    isStreaming: state.status === 'connecting' || state.status === 'streaming',
  }
}
```

### 三、ChatMessage.tsx 增强

```typescript
import { useState, useCallback } from 'react'
import { Typography, Dropdown, Button, Space, Tooltip, message } from 'antd'
import { CopyOutlined, EditOutlined, DeleteOutlined, ReplyOutlined, ReloadOutlined, MoreOutlined } from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

const { Text } = Typography

interface ChatMessageProps {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  isLoading?: boolean
  isEdited?: boolean
  knowledge_sources?: KnowledgeSource[]
  retrieval_info?: RetrievalInfo
  onEdit?: (id: string, content: string) => void
  onDelete?: (id: string) => void
  onReply?: (id: string) => void
  onRetry?: (id: string) => void
}

export default function ChatMessage({
  id,
  role,
  content,
  timestamp,
  isLoading,
  isEdited,
  knowledge_sources,
  retrieval_info,
  onEdit,
  onDelete,
  onReply,
  onRetry,
}: ChatMessageProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(content)
  const [showActions, setShowActions] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content)
    message.success('已复制到剪贴板')
  }, [content])

  const handleEdit = useCallback(() => {
    setIsEditing(true)
    setEditContent(content)
  }, [content])

  const handleSaveEdit = useCallback(() => {
    if (editContent.trim() !== content) {
      onEdit?.(id, editContent.trim())
    }
    setIsEditing(false)
  }, [editContent, content, id, onEdit])

  const handleCancelEdit = useCallback(() => {
    setIsEditing(false)
    setEditContent(content)
  }, [content])

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
      style={{
        display: 'flex',
        flexDirection: role === 'user' ? 'row-reverse' : 'row',
        gap: 12,
        marginBottom: 16,
        position: 'relative',
      }}
    >
      {/* 消息内容 */}
      <div
        style={{
          maxWidth: '80%',
          padding: '12px 16px',
          borderRadius: 12,
          background: role === 'user' ? 'var(--primary-color)' : 'var(--bg-secondary)',
          color: role === 'user' ? '#fff' : 'var(--text-primary)',
        }}
      >
        {isEditing ? (
          <div>
            <TextArea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              autoSize={{ minRows: 2, maxRows: 6 }}
              style={{ marginBottom: 8 }}
            />
            <Space>
              <Button size="small" onClick={handleCancelEdit}>取消</Button>
              <Button size="small" type="primary" onClick={handleSaveEdit}>保存</Button>
            </Space>
          </div>
        ) : (
          <>
            <ReactMarkdown
              components={{
                code({ node, inline, className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || '')
                  return !inline && match ? (
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match[1]}
                      PreTag="div"
                      {...props}
                    >
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  ) : (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  )
                },
              }}
            >
              {content}
            </ReactMarkdown>
            
            {isEdited && (
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                (已编辑)
              </Text>
            )}
          </>
        )}
        
        {/* 知识来源 */}
        {knowledge_sources && knowledge_sources.length > 0 && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-color)' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              📚 参考 {knowledge_sources.length} 个知识来源
            </Text>
          </div>
        )}
      </div>

      {/* 操作按钮 */}
      <AnimatePresence>
        {showActions && !isEditing && !isLoading && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            style={{
              position: 'absolute',
              top: 0,
              [role === 'user' ? 'left' : 'right']: -40,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            <Tooltip title="复制">
              <Button
                type="text"
                size="small"
                icon={<CopyOutlined />}
                onClick={handleCopy}
              />
            </Tooltip>
            
            {role === 'user' && onEdit && (
              <Tooltip title="编辑">
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={handleEdit}
                />
              </Tooltip>
            )}
            
            {role === 'assistant' && onRetry && (
              <Tooltip title="重新生成">
                <Button
                  type="text"
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => onRetry(id)}
                />
              </Tooltip>
            )}
            
            {onReply && (
              <Tooltip title="引用回复">
                <Button
                  type="text"
                  size="small"
                  icon={<ReplyOutlined />}
                  onClick={() => onReply(id)}
                />
              </Tooltip>
            )}
            
            {onDelete && (
              <Tooltip title="删除">
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => onDelete(id)}
                />
              </Tooltip>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* 时间戳 */}
      <Text
        type="secondary"
        style={{
          fontSize: 11,
          position: 'absolute',
          bottom: -16,
          [role === 'user' ? 'right' : 'left']: 0,
        }}
      >
        {new Date(timestamp).toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit',
        })}
      </Text>
    </motion.div>
  )
}
```

---

## 实施步骤

### 第一步：创建状态管理

```bash
# 创建文件
client/src/store/chatStore.ts
```

### 第二步：创建 Hooks

```bash
# 创建 hooks 目录
client/src/hooks/chat/
├── useChatMessages.ts
├── useChatStream.ts
├── useAgentExecutor.ts
├── useKnowledgeRetrieval.ts
└── useMemorySystem.ts
```

### 第三步：拆分组件

```bash
# 创建组件
client/src/components/chat/
├── ChatHeader.tsx
├── ChatMessageList.tsx
├── ChatMessage.tsx
├── ChatInput.tsx
├── AgentStatus.tsx
└── InputSuggestions.tsx
```

### 第四步：重构主页面

```bash
# 简化 Chat.tsx
client/src/pages/Chat.tsx  # 目标 < 300 行
```

---

## 验收标准

| 功能 | 验收标准 |
|------|----------|
| 消息发送 | 支持文本、Markdown、代码块 |
| 流式响应 | 实时显示、可中断、可重试 |
| 消息编辑 | 双击或点击编辑按钮 |
| 消息复制 | 一键复制、支持代码块 |
| 消息引用 | 引用回复、显示原文 |
| Agent 执行 | 状态展示、确认流程 |
| 知识库 | 检索结果展示、来源标注 |
| 性能 | 1000 条消息流畅滚动 |

---

**文档结束**
