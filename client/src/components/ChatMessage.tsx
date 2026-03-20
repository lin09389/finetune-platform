import React, { useState, useMemo, useCallback, memo } from 'react'
import { Button, Space, Tooltip, message, Slider, Tag } from 'antd'
import { CopyOutlined, ReloadOutlined, DeleteOutlined, CheckOutlined, SettingOutlined, BookOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import { motion, AnimatePresence } from 'framer-motion'
import CodePreview from '../components/CodePreview'
import StreamingMessage from '../components/StreamingMessage'
import ThinkingProcess from '../components/ThinkingProcess'
import type { KnowledgeSource, RetrievalInfo } from '../types'
import {
  messageVariants,
  buttonVariants,
  staggerContainer,
  staggerItem,
  typingIndicatorVariants,
  transitions,
} from '../theme/animations'
import 'highlight.js/styles/atom-one-dark.css'

interface ChatMessageProps {
  role: 'user' | 'assistant' | 'system'
  content: string
  thinkingContent?: string
  timestamp?: string
  onRetry?: () => void
  onDelete?: () => void
  isLoading?: boolean
  isStreaming?: boolean
  enableTypewriter?: boolean
  typewriterSpeed?: number
  knowledge_sources?: KnowledgeSource[]
  retrieval_info?: RetrievalInfo
}

const ChatMessage: React.FC<ChatMessageProps> = memo(
  ({
    role,
    content,
    thinkingContent,
    timestamp,
    onRetry,
    onDelete,
    isLoading = false,
    isStreaming = false,
    enableTypewriter = true,
    typewriterSpeed = 50,
    knowledge_sources,
    retrieval_info,
  }) => {
    const [copied, setCopied] = useState(false)
    const [showSpeedControl, setShowSpeedControl] = useState(false)
    const [currentSpeed, setCurrentSpeed] = useState(typewriterSpeed)
    const [showKnowledgeSources, setShowKnowledgeSources] = useState(false)

    const isUser = role === 'user'
    const isAssistant = role === 'assistant'

    const shouldUseStreaming = useMemo(() => {
      return isAssistant && enableTypewriter && isStreaming
    }, [isAssistant, enableTypewriter, isStreaming])

    const handleCopy = useCallback(async () => {
      try {
        await navigator.clipboard.writeText(content)
        setCopied(true)
        message.success('已复制到剪贴板')
        setTimeout(() => setCopied(false), 2000)
      } catch {
        message.error('复制失败')
      }
    }, [content])

    const formatTime = useCallback((timeStr?: string) => {
      if (!timeStr) return ''
      return new Date(timeStr).toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit',
      })
    }, [])

  return (
    <motion.div
      className={`chat-message ${isUser ? 'user' : 'assistant'}`}
      role="article"
      aria-label={isUser ? '用户消息' : 'AI 回复'}
      variants={messageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: isUser ? 'flex-end' : 'flex-start',
        marginBottom: '24px',
        width: '100%',
      }}
    >
      <motion.div
        className="message-bubble"
        role="region"
        aria-live={isUser ? 'off' : 'polite'}
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={transitions.spring}
        style={{
          padding: isUser ? '12px 18px' : '0',
          borderRadius: isUser ? '18px 18px 4px 18px' : '0',
          background: isUser ? 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)' : 'transparent',
          color: isUser ? '#fff' : 'var(--text-primary)',
          maxWidth: isUser ? '85%' : '100%',
          wordBreak: 'break-word',
          position: 'relative',
          boxShadow: isUser ? '0 2px 12px rgba(59, 130, 246, 0.25)' : 'none',
        }}
      >
        {isLoading ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{
              display: 'flex',
              gap: 6,
              padding: '8px 0',
              alignItems: 'center',
            }}
          >
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                variants={typingIndicatorVariants}
                initial="initial"
                animate="animate"
                transition={{ delay: i * 0.15 }}
                style={{
                  width: 8,
                  height: 8,
                  backgroundColor: isUser ? 'rgba(255,255,255,0.6)' : 'var(--text-tertiary)',
                  borderRadius: '50%',
                }}
              />
            ))}
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
              style={{
                marginLeft: 8,
                fontSize: '13px',
                color: isUser ? 'rgba(255,255,255,0.8)' : 'var(--text-secondary)',
              }}
            >
              思考中...
            </motion.span>
          </motion.div>
        ) : (
          <div 
            className="markdown-content"
            style={{ 
              fontSize: '15px', 
              lineHeight: 1.7,
              color: isUser ? '#fff' : 'var(--text-primary)',
            }}
          >
            {isUser ? (
              <div style={{ 
                color: '#fff',
                fontWeight: 500,
              }}>{content}</div>
            ) : shouldUseStreaming ? (
              <div style={{
                background: 'var(--bg-secondary)',
                borderRadius: '12px',
                padding: '16px 20px',
                border: '1px solid var(--border-color)',
              }}>
                {thinkingContent && (
                  <ThinkingProcess
                    content={thinkingContent}
                    isStreaming={isStreaming}
                  />
                )}
                <StreamingMessage
                  content={content}
                  isStreaming={isStreaming}
                  speed={currentSpeed}
                />
              </div>
            ) : (
              <div style={{
                background: 'var(--bg-secondary)',
                borderRadius: '12px',
                padding: '16px 20px',
                border: '1px solid var(--border-color)',
              }}>
                {thinkingContent && (
                  <ThinkingProcess
                    content={thinkingContent}
                  />
                )}
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeSanitize]}
                  components={{
                    code({ inline, className, children, ...props }: any) {
                      const match = /language-(\w+)/.exec(className || '')
                      const language = match ? match[1] : 'text'
                      
                      if (inline) {
                        return (
                          <code
                            style={{
                              backgroundColor: 'var(--bg-elevated)',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              fontSize: '0.9em',
                              color: 'var(--error)',
                              fontFamily: 'var(--font-mono)',
                            }}
                            {...props}
                          >
                            {children}
                          </code>
                        )
                      }

                      return (
                        <CodePreview
                          code={String(children)}
                          language={language}
                          showLineNumbers={true}
                          collapsible={false}
                          showFullscreen={true}
                          showSave={true}
                          defaultFilename={`code_${language}`}
                          maxHeight={400}
                        />
                      )
                    },
                    p: ({ children }) => <p style={{ margin: '8px 0' }}>{children}</p>,
                    ul: ({ children }) => <ul style={{ margin: '8px 0', paddingLeft: 24 }}>{children}</ul>,
                    ol: ({ children }) => <ol style={{ margin: '8px 0', paddingLeft: 24 }}>{children}</ol>,
                    li: ({ children }) => <li style={{ margin: '4px 0' }}>{children}</li>,
                    h1: ({ children }) => <h1 style={{ margin: '16px 0 8px', fontSize: 22, fontWeight: 700 }}>{children}</h1>,
                    h2: ({ children }) => <h2 style={{ margin: '14px 0 8px', fontSize: 18, fontWeight: 600 }}>{children}</h2>,
                    h3: ({ children }) => <h3 style={{ margin: '12px 0 6px', fontSize: 16, fontWeight: 600 }}>{children}</h3>,
                    blockquote: ({ children }) => (
                      <blockquote
                        style={{
                          margin: '12px 0',
                          padding: '8px 12px',
                          borderLeft: '3px solid var(--primary-500)',
                          background: 'var(--primary-50)',
                          borderRadius: '0 8px 8px 0',
                          fontStyle: 'italic',
                        }}
                      >
                        {children}
                      </blockquote>
                    ),
                    table: ({ children }) => (
                      <div style={{ overflowX: 'auto', margin: '12px 0', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>{children}</table>
                      </div>
                    ),
                    th: ({ children }) => (
                      <th
                        style={{
                          padding: '10px 12px',
                          background: 'var(--bg-elevated)',
                          fontWeight: 600,
                          borderBottom: '1px solid var(--border-color)',
                          textAlign: 'left',
                        }}
                      >
                        {children}
                      </th>
                    ),
                    td: ({ children }) => (
                      <td style={{ 
                        padding: '8px 12px', 
                        borderBottom: '1px solid var(--border-color)',
                      }}>
                        {children}
                      </td>
                    ),
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 5 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, ...transitions.base }}
        style={{
          display: 'flex',
          gap: 8,
          marginTop: 8,
          alignItems: 'center',
          padding: '0 4px',
          flexWrap: 'wrap',
        }}
      >
        <span style={{ 
          fontSize: '12px', 
          color: 'var(--text-tertiary)',
        }}>
          {formatTime(timestamp)}
        </span>
        
        {isAssistant && !isLoading && (
          <AnimatePresence mode="popLayout">
            <Space size={4}>
              <Tooltip title={copied ? '已复制' : '复制内容'}>
                <motion.div
                  variants={buttonVariants}
                  initial="initial"
                  whileHover="hover"
                  whileTap="tap"
                  style={{ display: 'inline-block' }}
                >
                  <Button
                    type="text"
                    size="small"
                    icon={copied ? <CheckOutlined style={{ color: 'var(--success)' }} /> : <CopyOutlined />}
                    onClick={handleCopy}
                    style={{ 
                      color: copied ? 'var(--success)' : 'var(--text-tertiary)',
                      padding: '2px 6px',
                      height: 'auto',
                      fontSize: '12px',
                    }}
                  />
                </motion.div>
              </Tooltip>
              {onRetry && (
                <Tooltip title="重新生成">
                  <motion.div
                    variants={buttonVariants}
                    initial="initial"
                    whileHover="hover"
                    whileTap="tap"
                    style={{ display: 'inline-block' }}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={onRetry}
                      style={{ 
                        color: 'var(--text-tertiary)',
                        padding: '2px 6px',
                        height: 'auto',
                        fontSize: '12px',
                      }}
                    />
                  </motion.div>
                </Tooltip>
              )}
              {onDelete && (
                <Tooltip title="删除消息">
                  <motion.div
                    variants={buttonVariants}
                    initial="initial"
                    whileHover="hover"
                    whileTap="tap"
                    style={{ display: 'inline-block' }}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={onDelete}
                      style={{ 
                        color: 'var(--error)',
                        padding: '2px 6px',
                        height: 'auto',
                        fontSize: '12px',
                      }}
                    />
                  </motion.div>
                </Tooltip>
              )}
              {enableTypewriter && (
                <Tooltip title="打字机速度设置">
                  <motion.div
                    variants={buttonVariants}
                    initial="initial"
                    whileHover="hover"
                    whileTap="tap"
                    style={{ display: 'inline-block' }}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<SettingOutlined />}
                      onClick={() => setShowSpeedControl(!showSpeedControl)}
                      style={{ 
                        color: showSpeedControl ? 'var(--primary-500)' : 'var(--text-tertiary)',
                        padding: '2px 6px',
                        height: 'auto',
                        fontSize: '12px',
                      }}
                    />
                  </motion.div>
                </Tooltip>
              )}
              {knowledge_sources && knowledge_sources.length > 0 && (
                <Tooltip title="查看知识来源">
                  <motion.div
                    variants={buttonVariants}
                    initial="initial"
                    whileHover="hover"
                    whileTap="tap"
                    style={{ display: 'inline-block' }}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<BookOutlined />}
                      onClick={() => setShowKnowledgeSources(!showKnowledgeSources)}
                      style={{ 
                        color: showKnowledgeSources ? 'var(--primary-500)' : 'var(--text-tertiary)',
                        padding: '2px 6px',
                        height: 'auto',
                        fontSize: '12px',
                      }}
                    >
                      <Tag color="blue" style={{ marginLeft: 4, fontSize: '10px', padding: '0 4px', lineHeight: '16px' }}>
                        {knowledge_sources.length}
                      </Tag>
                    </Button>
                  </motion.div>
                </Tooltip>
              )}
            </Space>
          </AnimatePresence>
        )}
        
        <AnimatePresence>
          {showSpeedControl && enableTypewriter && (
            <motion.div
              initial={{ opacity: 0, height: 0, scale: 0.9 }}
              animate={{ opacity: 1, height: 'auto', scale: 1 }}
              exit={{ opacity: 0, height: 0, scale: 0.9 }}
              transition={transitions.base}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '4px 12px',
                background: 'var(--bg-secondary)',
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                overflow: 'hidden',
              }}
            >
              <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>速度:</span>
              <Slider
                min={10}
                max={200}
                value={currentSpeed}
                onChange={setCurrentSpeed}
                style={{ width: 100, margin: 0 }}
                tooltip={{ formatter: (v) => `${v} 字符/秒` }}
              />
              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', minWidth: 60 }}>
              {currentSpeed} 字符/秒
            </span>
            </motion.div>
          )}
        </AnimatePresence>
        
        <AnimatePresence>
          {showKnowledgeSources && knowledge_sources && knowledge_sources.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0, y: -10 }}
              animate={{ opacity: 1, height: 'auto', y: 0 }}
              exit={{ opacity: 0, height: 0, y: -10 }}
              transition={transitions.slow}
              style={{
                marginTop: 8,
                width: '100%',
                background: 'var(--bg-secondary)',
                borderRadius: 12,
                border: '1px solid var(--border-color)',
                overflow: 'hidden',
              }}
            >
              <div style={{
                padding: '10px 14px',
                background: 'var(--bg-elevated)',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <Space>
                  <BookOutlined style={{ color: 'var(--primary-500)' }} />
                  <span style={{ fontWeight: 600, fontSize: '13px' }}>知识来源</span>
                  <Tag color="blue">{knowledge_sources.length} 条引用</Tag>
                </Space>
                {retrieval_info && (
                  <Space size={8}>
                    <Tooltip title="检索方法">
                      <Tag color="green">{retrieval_info.method}</Tag>
                    </Tooltip>
                    <Tooltip title="检索耗时">
                      <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                        {retrieval_info.retrieval_time.toFixed(3)}s
                      </span>
                    </Tooltip>
                  </Space>
                )}
              </div>
              <motion.div
                variants={staggerContainer}
                initial="initial"
                animate="animate"
                style={{ padding: '8px 12px', maxHeight: 200, overflowY: 'auto' }}
              >
                {knowledge_sources.map((source, index) => (
                  <motion.div
                    key={source.id}
                    variants={staggerItem}
                    style={{
                      padding: '8px 12px',
                      marginBottom: index < knowledge_sources.length - 1 ? 8 : 0,
                      background: 'var(--bg-color)',
                      borderRadius: 8,
                      border: '1px solid var(--border-color)',
                    }}
                  >
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: 4,
                    }}>
                      <Space>
                        <Tag color="geekblue">{index + 1}</Tag>
                        <span style={{
                          fontWeight: 500,
                          fontSize: '12px',
                          color: 'var(--text-primary)',
                        }}>
                          {source.source}
                        </span>
                      </Space>
                      <Tag color={source.score > 0.7 ? 'success' : source.score > 0.5 ? 'warning' : 'default'}>
                        {(source.score * 100).toFixed(1)}%
                      </Tag>
                    </div>
                    <div style={{
                      fontSize: '12px',
                      color: 'var(--text-secondary)',
                      lineHeight: 1.5,
                      padding: '4px 0 0 4px',
                    }}>
                      {source.content_preview}
                    </div>
                  </motion.div>
                ))}
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      <style>{`
        .markdown-content pre::-webkit-scrollbar {
          height: 8px;
          width: 8px;
        }
        
        .markdown-content pre::-webkit-scrollbar-track {
          background: transparent;
        }
        
        .markdown-content pre::-webkit-scrollbar-thumb {
          background: var(--border-color);
          border-radius: 4px;
        }
        
        .markdown-content pre::-webkit-scrollbar-thumb:hover {
          background: var(--text-tertiary);
        }
        
        @media (max-width: 768px) {
          .message-bubble {
            max-width: 90% !important;
          }
          
          .markdown-content {
            font-size: 14px !important;
          }
        }
      `}</style>
    </motion.div>
  )
})

export default ChatMessage
