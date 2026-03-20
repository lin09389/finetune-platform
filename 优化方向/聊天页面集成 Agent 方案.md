# 💬 聊天页面集成 Agent - 完整方案

## 🎯 核心目标

在**现有的 Chat.tsx**中直接集成 Agent 能力，用户聊天时就能操作电脑

---

## 📊 用户体验

### 现在的体验

```
用户："帮我打开 C:/test.txt"
AI:  "好的，这是打开文件的步骤：
      1. 打开文件管理器
      2. 导航到 C 盘
      3. 找到 test.txt
      4. 双击打开"

（用户需要自己操作）
```

### 集成后的体验

```
用户："帮我打开 C:/test.txt"
AI:  "好的，正在为您打开..."
     [执行操作：open_file]
     ✅ 已打开 C:/test.txt

（AI 直接操作）
```

---

## 🏗️ 技术方案

### 架构

```
┌─────────────────────────────────────────┐
│  Chat.tsx（现有聊天页面）                │
│  ┌─────────────────────────────────┐   │
│  │  消息列表                        │   │
│  │  - 普通消息                      │   │
│  │  - Agent 执行消息 ⭐              │   │
│  └─────────────────────────────────┘   │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│  新增：Agent 集成层                      │
│  ┌─────────────────────────────────┐   │
│  │  意图识别                        │   │
│  │  - 是否需要操作电脑              │   │
│  │  - 提取操作参数                  │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  执行 Agent 操作                  │   │
│  │  - 调用 Agent API                │   │
│  │  - 显示执行进度                  │   │
│  └─────────────────────────────────┘   │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│  server/agent/（现有 Agent 模块）        │
└─────────────────────────────────────────┘
```

---

## 📝 具体实现

### 第 1 步：修改 Chat.tsx

```tsx
// client/src/pages/Chat.tsx (修改版)

import { useState, useEffect, useRef } from 'react'
import { Card, Input, Button, Space, Empty, Badge, Dropdown, App, Alert, Progress } from 'antd'
import { SendOutlined, LoadingOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { streamInference, executeAgentTask } from '../services/api' // ⭐ 新增
import ChatMessage from '../components/ChatMessage'
import ChatHistoryDrawer from '../components/ChatHistoryDrawer'
import type { ChatMessage as ChatMessageType } from '../types'

const { TextArea } = Input

// ⭐ 新增：Agent 执行状态
interface AgentExecution {
  status: 'pending' | 'executing' | 'completed' | 'failed'
  action: string
  params: any
  progress: number
  error?: string
}

export default function Chat() {
  const { message } = App.useApp()
  const { backendStatus } = useAppStore()
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>()
  
  // ⭐ 新增：Agent 执行状态
  const [agentExecution, setAgentExecution] = useState<AgentExecution | null>(null)
  const [agentEnabled, setAgentEnabled] = useState(true) // 是否启用 Agent

  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollToBottom()
  }, [messages, agentExecution])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  // ⭐ 新增：检测是否需要执行 Agent 操作
  const detectAgentIntent = async (userMessage: string): Promise<{
    needAgent: boolean
    action?: string
    params?: any
    description?: string
  }> => {
    if (!agentEnabled) {
      return { needAgent: false }
    }

    try {
      // 调用 Agent API 检测意图
      const response = await fetch('http://127.0.0.1:8000/agent/detect-intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage
        })
      })

      if (response.ok) {
        const data = await response.json()
        return {
          needAgent: data.need_agent,
          action: data.action,
          params: data.params,
          description: data.description
        }
      }
    } catch (error) {
      console.warn('意图检测失败:', error)
    }

    return { needAgent: false }
  }

  // ⭐ 新增：执行 Agent 操作
  const executeAgent = async (action: string, params: any): Promise<{
    success: boolean
    result?: any
    error?: string
  }> => {
    setAgentExecution({
      status: 'executing',
      action,
      params,
      progress: 0
    })

    try {
      const response = await fetch('http://127.0.0.1:8000/agent/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_input: `${action} ${JSON.stringify(params)}`,
          require_confirm: false // 聊天中自动执行
        })
      })

      const result = await response.json()

      if (result.success) {
        setAgentExecution({
          status: 'completed',
          action,
          params,
          progress: 100
        })

        // 2 秒后清除状态
        setTimeout(() => setAgentExecution(null), 2000)

        return {
          success: true,
          result: result.results
        }
      } else {
        setAgentExecution({
          status: 'failed',
          action,
          params,
          progress: 0,
          error: result.error
        })

        return {
          success: false,
          error: result.error
        }
      }
    } catch (error) {
      setAgentExecution({
        status: 'failed',
        action,
        params,
        progress: 0,
        error: String(error)
      })

      return {
        success: false,
        error: String(error)
      }
    }
  }

  const handleSend = async () => {
    if (!selectedModel || !inputValue.trim()) return

    const userMessage: ChatMessageType = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date().toISOString(),
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setLoading(true)

    // ⭐ 新增：检测是否需要执行 Agent 操作
    const intent = await detectAgentIntent(userMessage.content)

    if (intent.needAgent && intent.action) {
      // 显示 Agent 执行状态
      setAgentExecution({
        status: 'pending',
        action: intent.action,
        params: intent.params,
        progress: 0
      })

      // 执行 Agent 操作
      const agentResult = await executeAgent(intent.action, intent.params)

      // 根据执行结果生成回复
      let aiResponse = ''
      if (agentResult.success) {
        aiResponse = `✅ ${intent.description || '操作已完成'}\n\n执行结果：${JSON.stringify(agentResult.result, null, 2)}`
      } else {
        aiResponse = `❌ 操作失败\n\n错误信息：${agentResult.error}`
      }

      // 添加 AI 回复
      const aiMessage: ChatMessageType = {
        id: `msg_${Date.now() + 1}`,
        role: 'assistant',
        content: aiResponse,
        timestamp: new Date().toISOString(),
      }

      setMessages(prev => [...prev, aiMessage])
      setLoading(false)

      return // 不再调用普通聊天
    }

    // ⭐ 普通聊天逻辑（保持不变）
    const assistantMessageId = `msg_${Date.now() + 1}`
    setMessages(prev => [...prev, {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isLoading: true,
    }])

    try {
      let fullResponse = ''
      
      await streamInference(
        {
          modelId: selectedModel,
          prompt: buildPrompt(messages, userMessage.content),
          maxTokens: 1024,
          temperature: 0.7,
        },
        (text: string) => {
          fullResponse += text
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId 
              ? { ...msg, content: fullResponse, isLoading: false }
              : msg
          ))
        }
      )
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : '推理失败'
      setMessages(prev => prev.map(msg => 
        msg.id === assistantMessageId 
          ? { ...msg, content: `错误：${errorMsg}`, isLoading: false }
          : msg
      ))
    } finally {
      setLoading(false)
    }
  }

  const buildPrompt = (history: ChatMessageType[], newMessage: string): string => {
    const recentHistory = history.slice(-10)
    let prompt = ''
    for (const msg of recentHistory) {
      if (msg.role === 'user') {
        prompt += `User: ${msg.content}\n`
      } else if (msg.role === 'assistant') {
        prompt += `Assistant: ${msg.content}\n`
      }
    }
    prompt += `Assistant: `
    return prompt
  }

  return (
    <div style={{ padding: '0 24px', height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      <div className="page-container" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* 顶部工具栏 */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
          padding: '12px 16px',
          background: '#fff',
          borderRadius: 8,
          boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
        }}>
          <Space>
            <Badge status={agentEnabled ? 'success' : 'error'} text={agentEnabled ? 'Agent 已启用' : 'Agent 已禁用'} />
          </Space>
          
          <Space>
            <Button 
              size="small"
              onClick={() => setAgentEnabled(!agentEnabled)}
              type={agentEnabled ? 'primary' : 'default'}
            >
              {agentEnabled ? '禁用 Agent' : '启用 Agent'}
            </Button>
          </Space>
        </div>

        {/* ⭐ 新增：Agent 执行状态显示 */}
        {agentExecution && (
          <Alert
            message={
              <Space>
                {agentExecution.status === 'executing' && <LoadingOutlined spin />}
                {agentExecution.status === 'completed' && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                {agentExecution.status === 'failed' && <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                <span>
                  {agentExecution.status === 'pending' && '准备执行...'}
                  {agentExecution.status === 'executing' && `正在执行：${agentExecution.action}`}
                  {agentExecution.status === 'completed' && '✅ 执行完成'}
                  {agentExecution.status === 'failed' && `❌ 执行失败：${agentExecution.error}`}
                </span>
              </Space>
            }
            type={
              agentExecution.status === 'failed' ? 'error' :
              agentExecution.status === 'completed' ? 'success' : 'info'
            }
            showIcon
            style={{ marginBottom: 16 }}
            action={
              agentExecution.status === 'executing' && (
                <Button size="small" danger onClick={() => setAgentExecution(null)}>
                  取消
                </Button>
              )
            }
          />
        )}

        {/* 聊天消息列表 */}
        <Card
          variant="borderless"
          styles={{ 
            body: { 
              flex: 1, 
              overflowY: 'auto', 
              padding: 24,
              background: '#fafafa',
            } 
          }}
        >
          {messages.length === 0 ? (
            <Empty 
              description="开始新的对话吧" 
              style={{ marginTop: 100 }}
            />
          ) : (
            <div>
              {messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  role={msg.role as 'user' | 'assistant'}
                  content={msg.content}
                  timestamp={msg.timestamp}
                  isLoading={msg.isLoading}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </Card>

        {/* 输入区域 */}
        <div style={{ 
          marginTop: 16, 
          padding: 16, 
          background: '#fff', 
          borderRadius: 8,
          boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
        }}>
          <TextArea
            placeholder={agentEnabled ? "输入指令，例如：打开 C:/test.txt" : "输入你的问题..."}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            rows={3}
            disabled={loading}
            style={{ marginBottom: 12, resize: 'none' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: '#999' }}>
              {selectedModel ? `当前模型：${selectedModel}` : '请选择模型'}
              {agentEnabled && ' · Agent 已启用'}
            </span>
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              loading={loading}
              disabled={!selectedModel || !inputValue.trim()}
            >
              发送
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
```

---

### 第 2 步：添加 API 服务

```typescript
// client/src/services/api.ts (新增)

/**
 * Agent 相关 API
 */

// 检测消息意图
export const detectAgentIntent = async (message: string) => {
  const response = await fetch('http://127.0.0.1:8000/agent/detect-intent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  })
  
  if (!response.ok) {
    throw new Error('意图检测失败')
  }
  
  return response.json()
}

// 执行 Agent 任务
export const executeAgentTask = async (
  user_input: string,
  require_confirm: boolean = false
) => {
  const response = await fetch('http://127.0.0.1:8000/agent/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_input, require_confirm })
  })
  
  if (!response.ok) {
    throw new Error('执行失败')
  }
  
  return response.json()
}
```

---

### 第 3 步：添加意图检测 API

```python
# server/api/agent.py (新增端点)

from fastapi import APIRouter
from pydantic import BaseModel
import re

router = APIRouter(prefix="/agent", tags=["Agent 操作"])

class IntentRequest(BaseModel):
    message: str

class IntentResponse(BaseModel):
    need_agent: bool
    action: str = None
    params: dict = None
    description: str = None

@router.post("/detect-intent", response_model=IntentResponse)
async def detect_intent(request: IntentRequest):
    """检测消息是否需要执行 Agent 操作"""
    
    message = request.message.lower()
    
    # 文件操作
    file_patterns = [
        (r'打开\s+(.+?\.(txt|pdf|doc|docx|jpg|png))', 'open_file', lambda m: {'file_path': m.group(1)}),
        (r'创建\s+(\S+)\s+文件', 'create_file', lambda m: {'file_path': m.group(1), 'content': ''}),
        (r'删除\s+(.+)', 'delete_file', lambda m: {'file_path': m.group(1)}),
        (r'移动\s+(.+?)\s+到\s+(.+)', 'move_file', lambda m: {'source': m.group(1), 'destination': m.group(2)}),
        (r'列出\s+(.+?)\s+的文件', 'list_files', lambda m: {'directory': m.group(1)}),
    ]
    
    # 应用操作
    app_patterns = [
        (r'打开\s+(VS ?Code|微信|QQ|浏览器|记事本)', 'open_app', lambda m: {'app_name': m.group(1)}),
        (r'关闭\s+(.+)', 'close_app', lambda m: {'app_name': m.group(1)}),
    ]
    
    # 浏览器操作
    browser_patterns = [
        (r'(https?://\S+)', 'open_url', lambda m: {'url': m.group(1)}),
        (r'打开网址\s+(\S+)', 'open_url', lambda m: {'url': m.group(1)}),
    ]
    
    # 检查所有模式
    all_patterns = file_patterns + app_patterns + browser_patterns
    
    for pattern, action, params_extractor in all_patterns:
        match = re.search(pattern, message)
        if match:
            return IntentResponse(
                need_agent=True,
                action=action,
                params=params_extractor(match),
                description=f"执行操作：{action}"
            )
    
    # 默认不需要 Agent
    return IntentResponse(need_agent=False)
```

---

### 第 4 步：优化 ChatMessage 组件

```tsx
// client/src/components/ChatMessage.tsx (优化版)

import { useState } from 'react'
import { Avatar, Button, Space, Tooltip, App } from 'antd'
import { UserOutlined, RobotOutlined, CopyOutlined, ReloadOutlined, DeleteOutlined, PlayCircleOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import 'highlight.js/styles/atom-one-dark.css'

interface ChatMessageProps {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp?: string
  onRetry?: () => void
  onDelete?: () => void
  isLoading?: boolean
  isAgentExecution?: boolean  // ⭐ 新增：是否是 Agent 执行消息
  agentAction?: string        // ⭐ 新增：Agent 操作
}

const ChatMessage: React.FC<ChatMessageProps> = ({
  role,
  content,
  timestamp,
  onRetry,
  onDelete,
  isLoading = false,
  isAgentExecution = false,
  agentAction,
}) => {
  const { message } = App.useApp()
  const [copied, setCopied] = useState(false)

  const isUser = role === 'user'
  const isAssistant = role === 'assistant'

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      message.success('已复制')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      message.error('复制失败')
    }
  }

  const formatTime = (timeStr?: string) => {
    if (!timeStr) return ''
    return new Date(timeStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' : 'row',
        gap: 12,
        marginBottom: 20,
        alignItems: 'flex-start',
      }}
    >
      <Avatar
        size={40}
        icon={
          isUser ? <UserOutlined /> : 
          isAgentExecution ? <PlayCircleOutlined /> : // ⭐ Agent 图标
          <RobotOutlined />
        }
        style={{
          backgroundColor: isUser ? '#1890ff' : 
                          isAgentExecution ? '#52c41a' : // ⭐ Agent 颜色
                          '#722ed1',
          flexShrink: 0,
        }}
      />

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          maxWidth: '70%',
          alignItems: isUser ? 'flex-end' : 'flex-start',
        }}
      >
        {isAgentExecution && (  // ⭐ Agent 执行标签
          <div style={{
            background: '#f6ffed',
            border: '1px solid #b7eb8f',
            borderRadius: 4,
            padding: '4px 8px',
            marginBottom: 8,
            fontSize: 12,
            color: '#52c41a'
          }}>
            🤖 Agent 执行：{agentAction}
          </div>
        )}

        <div
          style={{
            padding: '12px 16px',
            borderRadius: 12,
            backgroundColor: isUser ? '#1890ff' : '#fff',
            color: isUser ? '#fff' : '#333',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            wordBreak: 'break-word',
          }}
        >
          {isLoading ? (
            <div style={{ display: 'flex', gap: 4 }}>
              <span style={{ width: 8, height: 8, backgroundColor: '#999', borderRadius: '50%', animation: 'pulse 1s infinite' }} />
              <span style={{ width: 8, height: 8, backgroundColor: '#999', borderRadius: '50%', animation: 'pulse 1s infinite 0.2s' }} />
              <span style={{ width: 8, height: 8, backgroundColor: '#999', borderRadius: '50%', animation: 'pulse 1s infinite 0.4s' }} />
            </div>
          ) : (
            <div className="markdown-content" style={{ fontSize: 14, lineHeight: 1.6 }}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ node, inline, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || '')
                    const language = match ? match[1] : 'text'
                    
                    if (inline) {
                      return (
                        <code
                          style={{
                            backgroundColor: 'rgba(0,0,0,0.06)',
                            padding: '2px 6px',
                            borderRadius: 4,
                            fontSize: '0.9em',
                            color: '#e83e8c',
                          }}
                          {...props}
                        >
                          {children}
                        </code>
                      )
                    }

                    return (
                      <div style={{ position: 'relative', margin: '12px 0' }}>
                        <div
                          style={{
                            position: 'absolute',
                            right: 12,
                            top: 8,
                            fontSize: 12,
                            color: '#999',
                          }}
                        >
                          {language}
                        </div>
                        <pre style={{ margin: 0 }}>
                          <code className={className} {...props}>
                            {children}
                          </code>
                        </pre>
                      </div>
                    )
                  },
                  p: ({ children }) => <p style={{ margin: '8px 0' }}>{children}</p>,
                  ul: ({ children }) => <ul style={{ margin: '8px 0', paddingLeft: 20 }}>{children}</ul>,
                  ol: ({ children }) => <ol style={{ margin: '8px 0', paddingLeft: 20 }}>{children}</ol>,
                  li: ({ children }) => <li style={{ margin: '4px 0' }}>{children}</li>,
                  h1: ({ children }) => <h1 style={{ margin: '16px 0 8px', fontSize: 24 }}>{children}</h1>,
                  h2: ({ children }) => <h2 style={{ margin: '14px 0 6px', fontSize: 20 }}>{children}</h2>,
                  h3: ({ children }) => <h3 style={{ margin: '12px 0 4px', fontSize: 16 }}>{children}</h3>,
                  blockquote: ({ children, ...props }) => (
                    <blockquote
                      style={{
                        margin: '12px 0',
                        paddingLeft: 12,
                        borderLeft: '4px solid #1890ff',
                        backgroundColor: 'rgba(24, 144, 255, 0.1)',
                        padding: '8px 12px',
                      }}
                      {...props}
                    >
                      {children}
                    </blockquote>
                  ),
                  table: ({ children }) => (
                    <div style={{ overflowX: 'auto', margin: '12px 0' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>{children}</table>
                    </div>
                  ),
                  th: ({ children }) => (
                    <th
                      style={{
                        border: '1px solid #e8e8e8',
                        padding: '8px 12px',
                        backgroundColor: '#fafafa',
                        fontWeight: 600,
                      }}
                    >
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td style={{ border: '1px solid #e8e8e8', padding: '8px 12px' }}>{children}</td>
                  ),
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        <div
          style={{
            display: 'flex',
            gap: 8,
            marginTop: 6,
            opacity: isUser ? 1 : 0.8,
          }}
        >
          <span style={{ fontSize: 12, color: '#999' }}>{formatTime(timestamp)}</span>
          
          {isAssistant && !isLoading && !isAgentExecution && (
            <Space size={4}>
              <Tooltip title="复制">
                <Button
                  type="text"
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={handleCopy}
                  style={{ color: copied ? '#52c41a' : '#999' }}
                />
              </Tooltip>
              {onRetry && (
                <Tooltip title="重新生成">
                  <Button
                    type="text"
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={onRetry}
                    style={{ color: '#999' }}
                  />
                </Tooltip>
              )}
              {onDelete && (
                <Tooltip title="删除">
                  <Button
                    type="text"
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={onDelete}
                    style={{ color: '#ff4d4f' }}
                  />
                </Tooltip>
              )}
            </Space>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
        
        .markdown-content pre {
          background: #282c34;
          padding: 16px;
          border-radius: 8px;
          overflow-x: auto;
          margin: 12px 0;
        }
        
        .markdown-content code {
          font-family: 'Consolas', 'Monaco', monospace;
        }
        
        .markdown-content pre code {
          background: transparent;
          padding: 0;
        }
      `}</style>
    </div>
  )
}

export default ChatMessage
```

---

## 🎯 用户体验流程

### 完整流程

```
1. 用户输入："打开 C:/test.txt"
   ↓
2. 前端检测意图
   ↓
3. 调用 /agent/detect-intent
   ↓
4. 返回：need_agent=true, action=open_file
   ↓
5. 显示 Agent 执行状态
   ↓
6. 调用 /agent/execute
   ↓
7. 执行文件打开操作
   ↓
8. 显示执行结果
   ↓
9. 添加 AI 回复消息
```

---

## 🚀 开发计划

### 今晚（3 小时）

```
19:00-19:30   添加意图检测 API
              server/api/agent.py

19:30-21:00   修改 Chat.tsx
              集成 Agent 功能

21:00-22:00   测试基本功能
```

### 明晚（2 小时）

```
19:00-20:00   优化 ChatMessage
              添加 Agent 标识

20:00-21:00   完善错误处理
```

**总计：5 小时完成！**

---

## 💬 你的决定

**A. 立即开始** — 我帮你写第一步代码  
**B. 先看详细代码** — 查看完整实现  
**C. 调整方案** — 有其他想法？  
**D. 继续提问** — 还有疑问？  

**今晚就能在聊天中使用 Agent！** 🚀

告诉我你的选择！💪