import React, { useState, useCallback, useEffect, useRef } from 'react'
import { Button, Tooltip, message } from 'antd'
import { AudioOutlined, AudioMutedOutlined, LoadingOutlined } from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'

interface VoiceInputProps {
  onResult: (text: string) => void
  onError?: (error: string) => void
  language?: string
  continuous?: boolean
  disabled?: boolean
}

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList
  resultIndex: number
}

interface SpeechRecognitionErrorEvent {
  error: string
  message: string
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  start(): void
  stop(): void
  abort(): void
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  onstart: (() => void) | null
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognition
}

declare global {
  interface Window {
    SpeechRecognition: SpeechRecognitionConstructor
    webkitSpeechRecognition: SpeechRecognitionConstructor
  }
}

type RecognitionStatus = 'idle' | 'listening' | 'processing'

const VoiceInput: React.FC<VoiceInputProps> = ({
  onResult,
  onError,
  language = 'zh-CN',
  continuous = false,
  disabled = false,
}) => {
  const [status, setStatus] = useState<RecognitionStatus>('idle')
  const [interimText, setInterimText] = useState('')
  const [finalText, setFinalText] = useState('')
  const recognitionRef = useRef<SpeechRecognition | null>(null)

  const isSupported = typeof window !== 'undefined' && 
    (window.SpeechRecognition || window.webkitSpeechRecognition)

  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort()
      }
    }
  }, [])

  const initRecognition = useCallback(() => {
    if (!isSupported) return null

    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition
    const recognition = new SpeechRecognitionAPI()

    recognition.continuous = continuous
    recognition.interimResults = true
    recognition.lang = language

    recognition.onstart = () => {
      setStatus('listening')
      setInterimText('')
      setFinalText('')
    }

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = ''
      let final = ''

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (!result) continue
        const transcript = result[0]?.transcript
        if (!transcript) continue
        if (result.isFinal) {
          final += transcript
        } else {
          interim += transcript
        }
      }

      if (final) {
        setFinalText(prev => prev + final)
        onResult(final)
      }
      setInterimText(interim)
    }

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const errorMessage = getErrorMessage(event.error)
      setStatus('idle')
      setInterimText('')
      onError?.(errorMessage)
      message.error(errorMessage)
    }

    recognition.onend = () => {
      if (status === 'listening' && continuous) {
        try {
          recognition.start()
        } catch {
          setStatus('idle')
        }
      } else {
        setStatus('idle')
        setInterimText('')
      }
    }

    return recognition
  }, [isSupported, continuous, language, onResult, onError, status])

  const getErrorMessage = (error: string): string => {
    const errorMessages: Record<string, string> = {
      'no-speech': '未检测到语音输入',
      'audio-capture': '无法访问麦克风，请检查权限设置',
      'not-allowed': '麦克风权限被拒绝，请在浏览器设置中允许访问',
      'network': '网络错误，请检查网络连接',
      'aborted': '语音识别已取消',
      'service-not-allowed': '语音识别服务不可用',
      'language-not-supported': `不支持的语言: ${language}`,
    }
    return errorMessages[error] || `语音识别错误: ${error}`
  }

  const startRecognition = useCallback(() => {
    if (!isSupported) {
      message.warning('您的浏览器不支持语音识别功能')
      return
    }

    if (status === 'listening') {
      recognitionRef.current?.stop()
      return
    }

    const recognition = initRecognition()
    if (recognition) {
      recognitionRef.current = recognition
      try {
        recognition.start()
      } catch {
        message.error('启动语音识别失败')
        setStatus('idle')
      }
    }
  }, [isSupported, status, initRecognition])

  const stopRecognition = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
    }
    setStatus('idle')
    setInterimText('')
  }, [])

  const getButtonIcon = () => {
    switch (status) {
      case 'listening':
        return <AudioOutlined />
      case 'processing':
        return <LoadingOutlined />
      default:
        return <AudioMutedOutlined />
    }
  }

  const getButtonColor = () => {
    switch (status) {
      case 'listening':
        return 'var(--error)'
      case 'processing':
        return 'var(--warning)'
      default:
        return 'var(--text-secondary)'
    }
  }

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <Tooltip title={
        !isSupported 
          ? '浏览器不支持语音识别' 
          : status === 'listening' 
            ? '点击停止录音' 
            : '点击开始语音输入'
      }>
        <motion.div
          whileHover={{ scale: disabled ? 1 : 1.05 }}
          whileTap={{ scale: disabled ? 1 : 0.95 }}
        >
          <Button
            type={status === 'listening' ? 'primary' : 'text'}
            shape="circle"
            icon={getButtonIcon()}
            onClick={status === 'listening' ? stopRecognition : startRecognition}
            disabled={disabled || !isSupported}
            style={{
              width: 40,
              height: 40,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: status === 'listening' 
                ? 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)'
                : 'transparent',
              border: status === 'listening' 
                ? 'none' 
                : '1px solid var(--border-color)',
              color: status === 'listening' ? '#fff' : getButtonColor(),
              boxShadow: status === 'listening' 
                ? '0 4px 12px rgba(239, 68, 68, 0.4)' 
                : 'none',
            }}
          />
        </motion.div>
      </Tooltip>

      <AnimatePresence>
        {status === 'listening' && (
          <motion.div
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: 'auto' }}
            exit={{ opacity: 0, width: 0 }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              overflow: 'hidden',
            }}
          >
            <SoundWave />
            
            {(interimText || finalText) && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{
                  maxWidth: 200,
                  padding: '6px 12px',
                  background: 'var(--bg-secondary)',
                  borderRadius: 8,
                  border: '1px solid var(--border-color)',
                  fontSize: '13px',
                  color: 'var(--text-primary)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {finalText && <span>{finalText}</span>}
                {interimText && (
                  <span style={{ color: 'var(--text-tertiary)' }}>
                    {interimText}
                    <span style={{ animation: 'blink 1s infinite' }}>|</span>
                  </span>
                )}
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        @keyframes blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}

const SoundWave: React.FC = () => {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 2,
      height: 24,
      padding: '0 4px',
    }}>
      {[0, 1, 2, 3, 4].map((i) => (
        <motion.div
          key={i}
          animate={{
            height: [8, 20, 8],
          }}
          transition={{
            duration: 0.5,
            repeat: Infinity,
            delay: i * 0.1,
            ease: 'easeInOut',
          }}
          style={{
            width: 3,
            height: 8,
            background: 'linear-gradient(180deg, #ef4444 0%, #dc2626 100%)',
            borderRadius: 2,
          }}
        />
      ))}
    </div>
  )
}

export default VoiceInput
