import React, { useState, useRef, useEffect } from 'react'
import { Space, Tooltip } from 'antd'
import { 
  SendOutlined, 
  StopOutlined, 
  ClearOutlined,
  ThunderboltOutlined,
  SmileOutlined,
  PaperClipOutlined
} from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'
import NeumorphicButton from '../../../components/shared/NeumorphicButton'
import styles from './ChatInput.module.css'

interface ChatInputProps {
  onSend: (content: string) => void
  onStop: () => void
  onClear: () => void
  disabled: boolean
  loading: boolean
  isStreaming: boolean
  modelId: string | undefined
  suggestions?: string[]
}

const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  onStop,
  onClear,
  disabled,
  loading,
  isStreaming,
  modelId,
  suggestions = []
}) => {
  const [content, setContent] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    if (!content.trim() || disabled || loading || isStreaming) return
    onSend(content)
    setContent('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [content])

  return (
    <div className={styles.inputContainer}>
      {/* Suggestions */}
      <AnimatePresence>
        {content.length === 0 && !isStreaming && suggestions.length > 0 && (
          <motion.div 
            className={styles.suggestions}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
          >
            {suggestions.map((s, i) => (
              <motion.div
                key={i}
                className={styles.suggestionItem}
                onClick={() => setContent(s)}
                whileHover={{ scale: 1.02, x: 2 }}
                whileTap={{ scale: 0.98 }}
              >
                {s}
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <div className={styles.inputWrapper}>
        <div className={styles.toolbar}>
          <Space size="small">
            <Tooltip title="添加附件">
              <NeumorphicButton size="sm" variant="ghost" className={styles.toolBtn}>
                <PaperClipOutlined />
              </NeumorphicButton>
            </Tooltip>
            <Tooltip title="表情">
              <NeumorphicButton size="sm" variant="ghost" className={styles.toolBtn}>
                <SmileOutlined />
              </NeumorphicButton>
            </Tooltip>
          </Space>
          
          <div className={styles.modelBadge}>
            <ThunderboltOutlined style={{ color: 'var(--accent-primary)' }} />
            <span>{modelId || '未选择模型'}</span>
          </div>
        </div>

        <div className={styles.textAreaBox}>
          <textarea
            ref={textareaRef}
            rows={1}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "请先选择一个模型..." : "输入消息，Shift + Enter 换行"}
            className={styles.textarea}
            disabled={disabled}
          />
          
          <div className={styles.actions}>
            <Space size="middle">
              <Tooltip title="清空对话">
                <NeumorphicButton 
                  size="sm" 
                  variant="ghost" 
                  onClick={onClear}
                  disabled={loading || isStreaming}
                >
                  <ClearOutlined />
                </NeumorphicButton>
              </Tooltip>

              {isStreaming ? (
                <NeumorphicButton 
                  size="md" 
                  variant="danger" 
                  onClick={onStop}
                >
                  <StopOutlined />
                  <span className={styles.btnText}>停止生成</span>
                </NeumorphicButton>
              ) : (
                <NeumorphicButton 
                  size="md" 
                  variant="primary" 
                  onClick={handleSend}
                  disabled={!content.trim() || disabled || loading}
                >
                  <SendOutlined />
                  <span className={styles.btnText}>发送</span>
                </NeumorphicButton>
              )}
            </Space>
          </div>
        </div>
      </div>
      
      <div className={styles.footer}>
        AI 生成的内容可能不准确，请注意甄别。
      </div>
    </div>
  )
}

export default ChatInput
