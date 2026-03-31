import React, { useState, useCallback, useRef, useEffect } from 'react'
import { Input, Button, Tooltip, message, Avatar, Typography } from 'antd'
import { SendOutlined, AudioOutlined, StopOutlined, RobotOutlined, ThunderboltOutlined, ClearOutlined } from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'
import { transitions } from '../../theme/animations'

const { TextArea } = Input
const { Text } = Typography

interface ChatInputProps {
  onSend: (content: string) => void
  onStop?: () => void
  onClear?: () => void
  disabled?: boolean
  loading?: boolean
  isStreaming?: boolean
  placeholder?: string
  modelId?: string
  maxLength?: number
  showModelInfo?: boolean
  suggestions?: string[]
  onSuggestionClick?: (suggestion: string) => void
}

const DEFAULT_SUGGESTIONS = [
  '帮我解释一下这个概念',
  '写一段代码实现...',
  '分析这个问题',
  '总结一下要点',
]

const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  onStop,
  onClear,
  disabled = false,
  loading = false,
  isStreaming = false,
  placeholder = '输入你的问题... (Shift+Enter 换行)',
  modelId,
  maxLength = 4000,
  showModelInfo = true,
  suggestions = DEFAULT_SUGGESTIONS,
  onSuggestionClick,
}) => {
  const [value, setValue] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [isRecording, setIsRecording] = useState(false)

  const canSend = value.trim().length > 0 && !disabled && !loading

  const handleSend = useCallback(() => {
    if (!canSend) return
    
    onSend(value.trim())
    setValue('')
    setShowSuggestions(false)
  }, [canSend, onSend, value])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (isStreaming) {
        onStop?.()
      } else {
        handleSend()
      }
    }
  }, [handleSend, isStreaming, onStop])

  const handleSuggestionClick = useCallback((suggestion: string) => {
    setValue(suggestion)
    setShowSuggestions(false)
    textareaRef.current?.focus()
    onSuggestionClick?.(suggestion)
  }, [onSuggestionClick])

  const handleVoiceInput = useCallback(() => {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      message.warning('您的浏览器不支持语音输入')
      return
    }

    const SpeechRecognition = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
    const recognition = new SpeechRecognition()
    
    recognition.lang = 'zh-CN'
    recognition.continuous = false
    recognition.interimResults = true

    recognition.onstart = () => {
      setIsRecording(true)
      message.info('开始录音...')
    }

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript
      setValue((prev) => prev + transcript)
    }

    recognition.onerror = (event: any) => {
      console.error('语音识别错误:', event.error)
      message.error('语音识别失败')
      setIsRecording(false)
    }

    recognition.onend = () => {
      setIsRecording(false)
    }

    recognition.start()
  }, [])

  const focusInput = useCallback(() => {
    textareaRef.current?.focus()
  }, [])

  useEffect(() => {
    const handleGlobalShortcut = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== textareaRef.current) {
        e.preventDefault()
        focusInput()
      }
    }

    window.addEventListener('keydown', handleGlobalShortcut)
    return () => window.removeEventListener('keydown', handleGlobalShortcut)
  }, [focusInput])

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3, ...transitions.base }}
      style={{
        padding: '16px 24px 24px',
        background: 'var(--bg-primary)',
        borderTop: '1px solid var(--border-color)',
      }}
    >
      <div style={{ maxWidth: 768, margin: '0 auto' }}>
        <AnimatePresence>
          {showSuggestions && suggestions.length > 0 && !value && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={transitions.base}
              style={{
                marginBottom: 12,
                display: 'flex',
                gap: 8,
                flexWrap: 'wrap',
                overflow: 'hidden',
              }}
            >
              {suggestions.map((suggestion, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: index * 0.05 }}
                >
                  <Button
                    size="small"
                    onClick={() => handleSuggestionClick(suggestion)}
                    style={{
                      borderRadius: 16,
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-secondary)',
                      fontSize: 13,
                    }}
                  >
                    {suggestion}
                  </Button>
                </motion.div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        <motion.div
          animate={{
            boxShadow: isFocused 
              ? '0 0 0 2px var(--primary-500), 0 4px 12px rgba(59, 130, 246, 0.15)'
              : '0 2px 8px rgba(0, 0, 0, 0.04)',
          }}
          transition={transitions.base}
          style={{
            background: 'var(--bg-secondary)',
            borderRadius: 16,
            border: '1px solid var(--border-color)',
            padding: '12px 16px',
            transition: 'box-shadow 0.3s ease',
          }}
        >
          <TextArea
            ref={textareaRef}
            placeholder={disabled ? '请先选择模型' : placeholder}
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              if (e.target.value.length === 0) {
                setShowSuggestions(true)
              } else {
                setShowSuggestions(false)
              }
            }}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              setIsFocused(true)
              if (!value) setShowSuggestions(true)
            }}
            onBlur={() => {
              setIsFocused(false)
              setTimeout(() => setShowSuggestions(false), 200)
            }}
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={disabled || loading}
            maxLength={maxLength}
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
          
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 12,
            paddingTop: 12,
            borderTop: '1px solid var(--border-color)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {showModelInfo && modelId ? (
                <>
                  <Avatar
                    size={24}
                    icon={<RobotOutlined />}
                    style={{ 
                      background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                      width: 24,
                      height: 24,
                    }}
                  />
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    {modelId}
                  </Text>
                </>
              ) : (
                <Text type="secondary" style={{ fontSize: 13 }}>
                  请先选择模型
                </Text>
              )}
              
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                {value.length}/{maxLength}
              </Text>
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Tooltip title="快捷输入建议">
                <Button
                  type="text"
                  size="small"
                  icon={<ThunderboltOutlined />}
                  onClick={() => setShowSuggestions(!showSuggestions)}
                  style={{ 
                    color: showSuggestions ? 'var(--primary-500)' : 'var(--text-tertiary)',
                  }}
                />
              </Tooltip>
              
              <Tooltip title="语音输入">
                <Button
                  type="text"
                  size="small"
                  icon={<AudioOutlined />}
                  onClick={handleVoiceInput}
                  danger={isRecording}
                  style={{ 
                    color: isRecording ? 'var(--error)' : 'var(--text-tertiary)',
                  }}
                />
              </Tooltip>
              
              {onClear && (
                <Tooltip title="清空对话">
                  <Button
                    type="text"
                    size="small"
                    icon={<ClearOutlined />}
                    onClick={onClear}
                    style={{ color: 'var(--text-tertiary)' }}
                  />
                </Tooltip>
              )}
              
              {isStreaming ? (
                <motion.div
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Button
                    type="primary"
                    danger
                    icon={<StopOutlined />}
                    onClick={onStop}
                    style={{
                      borderRadius: 8,
                      height: 36,
                      padding: '0 16px',
                    }}
                  >
                    停止
                  </Button>
                </motion.div>
              ) : (
                <motion.div
                  whileHover={{ scale: canSend ? 1.02 : 1 }}
                  whileTap={{ scale: canSend ? 0.98 : 1 }}
                >
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    disabled={!canSend}
                    style={{
                      borderRadius: 8,
                      height: 36,
                      padding: '0 20px',
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
        
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          marginTop: 8,
        }}>
          <Text type="secondary" style={{ fontSize: 11 }}>
            按 Enter 发送 · Shift+Enter 换行 · 按 / 快速聚焦
          </Text>
        </div>
      </div>
    </motion.div>
  )
}

export default ChatInput
