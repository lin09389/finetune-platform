import React, { useState, useEffect } from 'react'
import { Button, Tooltip, Space, Typography, Popconfirm } from 'antd'
import { 
  StopOutlined, 
  SaveOutlined, 
  LoadingOutlined,
  ThunderboltOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'
import { transitions } from '../theme/animations'

const { Text } = Typography

interface StopButtonProps {
  onStop: () => void
  onSavePartial?: () => void
  hasPartialContent?: boolean
  partialContentLength?: number
  size?: 'small' | 'middle' | 'large'
  variant?: 'default' | 'compact' | 'extended'
}

export const StopButton: React.FC<StopButtonProps> = ({
  onStop,
  onSavePartial,
  hasPartialContent = false,
  partialContentLength = 0,
  size = 'middle',
  variant = 'default',
}) => {
  const [isStopping, setIsStopping] = useState(false)
  const [showSaveOption, setShowSaveOption] = useState(false)
  const [pulseAnimation, setPulseAnimation] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => {
      setPulseAnimation(prev => !prev)
    }, 1500)
    return () => clearInterval(interval)
  }, [])

  const handleStop = () => {
    setIsStopping(true)
    onStop()
    setTimeout(() => setIsStopping(false), 500)
  }

  const handleSaveAndStop = () => {
    if (onSavePartial) {
      onSavePartial()
    }
    handleStop()
  }

  if (variant === 'compact') {
    return (
      <Tooltip title="停止生成">
        <motion.div
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Button
            danger
            type="primary"
            icon={isStopping ? <LoadingOutlined spin /> : <StopOutlined />}
            onClick={handleStop}
            size={size}
            style={{
              borderRadius: 8,
            }}
          />
        </motion.div>
      </Tooltip>
    )
  }

  if (variant === 'extended') {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        style={{ display: 'flex', gap: 8 }}
      >
        <Popconfirm
          title="停止生成"
          description={
            hasPartialContent ? (
              <Space direction="vertical" size={4}>
                <Text>已生成 {partialContentLength} 字符</Text>
                <Text type="secondary">是否保存已生成的内容？</Text>
              </Space>
            ) : (
              '确定要停止生成吗？'
            )
          }
          onConfirm={hasPartialContent && onSavePartial ? handleSaveAndStop : handleStop}
          onCancel={hasPartialContent ? handleStop : undefined}
          okText={hasPartialContent ? '保存并停止' : '停止'}
          cancelText={hasPartialContent ? '直接停止' : '取消'}
          okButtonProps={{ danger: true }}
        >
          <motion.div
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Button
              danger
              type="primary"
              icon={isStopping ? <LoadingOutlined spin /> : <StopOutlined />}
              size={size}
              style={{
                borderRadius: 8,
                height: 36,
                padding: '0 20px',
                fontSize: 14,
                fontWeight: 500,
              }}
            >
              停止生成
            </Button>
          </motion.div>
        </Popconfirm>
      </motion.div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      onHoverStart={() => setShowSaveOption(true)}
      onHoverEnd={() => setShowSaveOption(false)}
      style={{ display: 'inline-flex', gap: 8 }}
    >
      <motion.div
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        animate={{
          boxShadow: pulseAnimation 
            ? '0 0 0 0 rgba(255, 77, 79, 0.4)' 
            : '0 0 0 8px rgba(255, 77, 79, 0)',
        }}
        transition={{ duration: 1.5 }}
      >
        <Button
          danger
          type="primary"
          icon={isStopping ? <LoadingOutlined spin /> : <StopOutlined />}
          onClick={handleStop}
          size={size}
          style={{
            borderRadius: 8,
            height: 36,
            padding: '0 20px',
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          停止
        </Button>
      </motion.div>

      <AnimatePresence>
        {showSaveOption && hasPartialContent && onSavePartial && (
          <motion.div
            initial={{ opacity: 0, x: -10, width: 0 }}
            animate={{ opacity: 1, x: 0, width: 'auto' }}
            exit={{ opacity: 0, x: -10, width: 0 }}
            transition={transitions.fast}
          >
            <Tooltip title={`保存已生成的 ${partialContentLength} 字符`}>
              <Button
                icon={<SaveOutlined />}
                onClick={handleSaveAndStop}
                size={size}
                style={{
                  borderRadius: 8,
                  height: 36,
                }}
              >
                保存
              </Button>
            </Tooltip>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

interface StreamingIndicatorProps {
  isActive: boolean
  contentLength: number
  speed?: number
}

export const StreamingIndicator: React.FC<StreamingIndicatorProps> = ({
  isActive,
  contentLength,
  speed,
}) => {
  if (!isActive) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '4px 12px',
        background: 'linear-gradient(135deg, rgba(24, 144, 255, 0.1), rgba(82, 196, 26, 0.1))',
        borderRadius: 16,
        border: '1px solid rgba(24, 144, 255, 0.2)',
      }}
    >
      <motion.div
        animate={{
          scale: [1, 1.2, 1],
          opacity: [0.7, 1, 0.7],
        }}
        transition={{
          duration: 1.5,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      >
        <ThunderboltOutlined style={{ color: '#1890ff', fontSize: 14 }} />
      </motion.div>
      
      <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
        {contentLength} 字符
      </Text>

      {speed && speed > 0 && (
        <Text style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
          {speed.toFixed(1)} 字/秒
        </Text>
      )}
    </motion.div>
  )
}

interface InterruptedContentBannerProps {
  content: string
  onContinue?: () => void
  onSave?: () => void
  onDiscard?: () => void
}

export const InterruptedContentBanner: React.FC<InterruptedContentBannerProps> = ({
  content,
  onContinue,
  onSave,
  onDiscard,
}) => {
  if (!content) return null

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      style={{
        padding: '12px 16px',
        background: 'rgba(250, 173, 20, 0.1)',
        border: '1px solid rgba(250, 173, 20, 0.3)',
        borderRadius: 8,
        marginBottom: 12,
      }}
    >
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space>
          <PauseCircleOutlined style={{ color: '#faad14' }} />
          <Text strong style={{ color: '#d48806' }}>
            生成已中断
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            已生成 {content.length} 字符
          </Text>
        </Space>

        <div
          style={{
            maxHeight: 100,
            overflow: 'auto',
            padding: '8px 12px',
            background: 'var(--bg-primary)',
            borderRadius: 4,
            border: '1px solid var(--border-color)',
          }}
        >
          <Text
            style={{
              fontSize: 12,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {content.slice(0, 200)}
            {content.length > 200 && '...'}
          </Text>
        </div>

        <Space>
          {onContinue && (
            <Button
              type="primary"
              size="small"
              icon={<ThunderboltOutlined />}
              onClick={onContinue}
              style={{ borderRadius: 6 }}
            >
              继续生成
            </Button>
          )}
          {onSave && (
            <Button
              size="small"
              icon={<SaveOutlined />}
              onClick={onSave}
              style={{ borderRadius: 6 }}
            >
              保存内容
            </Button>
          )}
          {onDiscard && (
            <Button
              size="small"
              danger
              onClick={onDiscard}
              style={{ borderRadius: 6 }}
            >
              丢弃
            </Button>
          )}
        </Space>
      </Space>
    </motion.div>
  )
}

export default StopButton
