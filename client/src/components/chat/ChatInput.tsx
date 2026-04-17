import {
  AudioOutlined,
  ClearOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Input, Tooltip, Typography, message } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useResponsive } from '../../hooks/useResponsive';
import { transitions } from '../../theme/animations';
import styles from './ChatInput.module.css';

const { TextArea } = Input;
const { Text } = Typography;

interface ChatInputProps {
  onSend: (content: string) => void;
  onStop?: () => void;
  onClear?: () => void;
  disabled?: boolean;
  loading?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  modelId?: string;
  maxLength?: number;
  showModelInfo?: boolean;
  suggestions?: string[];
  onSuggestionClick?: (suggestion: string) => void;
}

const DEFAULT_SUGGESTIONS = [
  '帮我解释一下这个概念',
  '写一段代码实现...',
  '分析这个问题',
  '总结一下要点',
];

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
  const { isMobile } = useResponsive();
  const [value, setValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isRecording, setIsRecording] = useState(false);

  const canSend = value.trim().length > 0 && !disabled && !loading;

  const handleSend = useCallback(() => {
    if (!canSend) return;
    onSend(value.trim());
    setValue('');
    setShowSuggestions(false);
  }, [canSend, onSend, value]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (isStreaming) {
          onStop?.();
        } else {
          handleSend();
        }
      }
    },
    [handleSend, isStreaming, onStop],
  );

  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      setValue(suggestion);
      setShowSuggestions(false);
      textareaRef.current?.focus();
      onSuggestionClick?.(suggestion);
    },
    [onSuggestionClick],
  );

  const handleVoiceInput = useCallback(() => {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      message.warning('当前浏览器不支持语音输入');
      return;
    }

    const SpeechRecognition =
      (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    const recognition = new SpeechRecognition();

    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
      setIsRecording(true);
      message.info('开始录音...');
    };

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setValue((prev) => prev + transcript);
    };

    recognition.onerror = (event: any) => {
      console.error('Voice input error:', event.error);
      message.error('语音识别失败');
      setIsRecording(false);
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognition.start();
  }, []);

  const focusInput = useCallback(() => {
    textareaRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleGlobalShortcut = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== textareaRef.current) {
        e.preventDefault();
        focusInput();
      }
    };

    window.addEventListener('keydown', handleGlobalShortcut);
    return () => window.removeEventListener('keydown', handleGlobalShortcut);
  }, [focusInput]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.24, ...transitions.base }}
      className={`${styles.inputShell} ${isMobile ? styles.inputShellMobile : styles.inputShellDesktop}`}
    >
      <div className={styles.container}>
        <AnimatePresence>
          {showSuggestions && suggestions.length > 0 && !value && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={transitions.base}
              className={styles.suggestions}
            >
              {suggestions.map((suggestion, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, scale: 0.92 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: index * 0.04 }}
                >
                  <Button
                    size="small"
                    onClick={() => handleSuggestionClick(suggestion)}
                    className={styles.suggestionBtn}
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
              ? '0 8px 32px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.06), inset 0 0 0 1px var(--text-tertiary)'
              : '0 8px 32px rgba(0, 0, 0, 0.04), 0 2px 8px rgba(0, 0, 0, 0.02)',
          }}
          transition={transitions.base}
          className={`${styles.editorCard} ${isMobile ? styles.editorCardMobile : styles.editorCardDesktop}`}
        >
          <TextArea
            ref={textareaRef}
            placeholder={disabled ? '请先选择模型' : placeholder}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (e.target.value.length === 0) {
                setShowSuggestions(true);
              } else {
                setShowSuggestions(false);
              }
            }}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              setIsFocused(true);
              if (!value) setShowSuggestions(true);
            }}
            onBlur={() => {
              setIsFocused(false);
              setTimeout(() => setShowSuggestions(false), 200);
            }}
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={disabled || loading}
            maxLength={maxLength}
            className={styles.textarea}
          />

          <div className={styles.toolbar}>
            <div className={styles.toolbarLeft}>
              {showModelInfo && modelId ? (
                <>
                  <Avatar
                    size={24}
                    icon={<RobotOutlined />}
                    style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
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

            <div className={styles.toolbarRight}>
              <Tooltip title="快捷建议">
                <Button
                  type="text"
                  size="small"
                  icon={<ThunderboltOutlined />}
                  onClick={() => setShowSuggestions(!showSuggestions)}
                  style={{ color: showSuggestions ? 'var(--accent-primary)' : undefined }}
                  className={styles.ghostIcon}
                />
              </Tooltip>

              <Tooltip title="语音输入">
                <Button
                  type="text"
                  size="small"
                  icon={<AudioOutlined />}
                  onClick={handleVoiceInput}
                  danger={isRecording}
                  className={styles.ghostIcon}
                />
              </Tooltip>

              {onClear && (
                <Tooltip title="清空对话">
                  <Button
                    type="text"
                    size="small"
                    icon={<ClearOutlined />}
                    onClick={onClear}
                    className={styles.ghostIcon}
                  />
                </Tooltip>
              )}

              {isStreaming ? (
                <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                  <Button
                    type="primary"
                    danger
                    icon={<StopOutlined />}
                    onClick={onStop}
                    className={styles.stopBtn}
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
                    className={styles.sendBtn}
                  >
                    发送
                  </Button>
                </motion.div>
              )}
            </div>
          </div>
        </motion.div>

        <div className={styles.hint}>
          <Text type="secondary" style={{ fontSize: 11 }}>
            按 Enter 发送 · Shift+Enter 换行 · 按 / 快速聚焦
          </Text>
        </div>
      </div>
    </motion.div>
  );
};

export default ChatInput;
