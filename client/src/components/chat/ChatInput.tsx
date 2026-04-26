import {
  AudioOutlined,
  ClearOutlined,
  PartitionOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Input, Select, Tooltip, Typography, message } from 'antd';
import { motion } from 'framer-motion';
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
  onCreateWorkflow?: (content: string) => void | Promise<void>;
  creatingWorkflow?: boolean;
  workflowTemplateOptions?: Array<{ value: string; label: string }>;
  selectedWorkflowTemplate?: string;
  onWorkflowTemplateChange?: (templateId: string) => void;
}

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
  onCreateWorkflow,
  creatingWorkflow = false,
  workflowTemplateOptions = [],
  selectedWorkflowTemplate = 'software_delivery',
  onWorkflowTemplateChange,
}) => {
  const { isMobile } = useResponsive();
  const [value, setValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isRecording, setIsRecording] = useState(false);

  const canSend = value.trim().length > 0 && !disabled && !loading;

  const handleSend = useCallback(() => {
    if (!canSend) return;
    onSend(value.trim());
    setValue('');
  }, [canSend, onSend, value]);

  const handleCreateWorkflow = useCallback(async () => {
    const content = value.trim();
    if (!content) {
      message.warning('请先输入工作流目标');
      return;
    }
    await onCreateWorkflow?.(content);
  }, [onCreateWorkflow, value]);

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
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
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

              {onCreateWorkflow && (
                <>
                  {workflowTemplateOptions.length > 1 && (
                    <Select
                      size="small"
                      value={selectedWorkflowTemplate}
                      options={workflowTemplateOptions}
                      onChange={onWorkflowTemplateChange}
                      style={{ minWidth: 128 }}
                      disabled={loading || isStreaming || creatingWorkflow}
                    />
                  )}
                  <Tooltip title="发起工作流">
                    <Button
                      type="text"
                      size="small"
                      icon={<PartitionOutlined />}
                      onClick={handleCreateWorkflow}
                      loading={creatingWorkflow}
                      disabled={loading || isStreaming}
                      className={styles.ghostIcon}
                    />
                  </Tooltip>
                </>
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
