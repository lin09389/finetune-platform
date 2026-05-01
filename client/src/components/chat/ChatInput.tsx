import {
  AudioOutlined,
  ClearOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Input, Segmented, Select, Tooltip, Typography, message } from 'antd';
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
  agentModeAvailable?: boolean;
  onCreateWorkflow?: (content: string) => void | Promise<void>;
  creatingWorkflow?: boolean;
  workflowTemplateOptions?: Array<{ value: string; label: string }>;
  selectedWorkflowTemplate?: string;
  onWorkflowTemplateChange?: (templateId: string) => void;
  agentOptions?: Array<{ value: string; label: string }>;
  selectedAgent?: string;
  onAgentChange?: (agentId: string) => void;
  routingMode?: 'auto' | 'chat' | 'agent';
  onRoutingModeChange?: (mode: 'auto' | 'chat' | 'agent') => void;
  routing?: boolean;
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
  agentModeAvailable = false,
  onCreateWorkflow,
  creatingWorkflow = false,
  workflowTemplateOptions = [],
  selectedWorkflowTemplate = 'software_delivery',
  onWorkflowTemplateChange,
  agentOptions = [],
  selectedAgent = 'build',
  onAgentChange,
  routingMode = 'auto',
  onRoutingModeChange,
  routing = false,
}) => {
  const { isMobile } = useResponsive();
  const [value, setValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isRecording, setIsRecording] = useState(false);

  const inputDisabled = disabled && !agentModeAvailable;
  const routingMeta = {
    auto: {
      label: routing ? '正在判断路由' : '自动路由',
      hint: routing ? '正在判断是否需要 Agent' : '开发任务会自动进入 Agent',
    },
    chat: {
      label: '普通对话',
      hint: '本次只发送普通聊天',
    },
    agent: {
      label: 'Agent 工作',
      hint: '发送后直接启动 Agent',
    },
  }[routingMode];
  const canSend =
    value.trim().length > 0 &&
    (!disabled || (agentModeAvailable && routingMode !== 'chat')) &&
    !loading &&
    !routing;

  const handleCreateWorkflow = useCallback(async () => {
    const content = value.trim();
    if (!content) {
      message.warning('先输入一个要让 Agent 完成的目标');
      return;
    }
    await onCreateWorkflow?.(content);
    setValue('');
  }, [onCreateWorkflow, value]);

  const handleSend = useCallback(async () => {
    if (!canSend) return;
    if (disabled && agentModeAvailable && routingMode !== 'chat' && onCreateWorkflow) {
      await handleCreateWorkflow();
      return;
    }
    onSend(value.trim());
    setValue('');
  }, [agentModeAvailable, canSend, disabled, handleCreateWorkflow, onCreateWorkflow, onSend, routingMode, value]);

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
            placeholder={inputDisabled ? '请先选择模型' : placeholder}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={inputDisabled || loading}
            maxLength={maxLength}
            bordered={false}
            className={styles.textarea}
          />

          {onCreateWorkflow && (
            <div className={styles.routeStatus}>
              <div className={`${styles.routePulse} ${styles[`routePulse_${routingMode}`]} ${routing ? styles.routePulseActive : ''}`} />
              <Text className={styles.routeLabel}>{routingMeta.label}</Text>
              <Text className={styles.routeHint}>{routingMeta.hint}</Text>
              {agentOptions.length > 0 && routingMode !== 'chat' && (
                <Text className={styles.routeAgent}>Agent: {selectedAgent}</Text>
              )}
            </div>
          )}

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
                  {agentModeAvailable ? 'Agent 模式可用' : '请先选择模型'}
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
                  {agentOptions.length > 0 && (
                    <Select
                      size="small"
                      value={selectedAgent}
                      options={agentOptions}
                      onChange={onAgentChange}
                      style={{ minWidth: 128 }}
                      disabled={loading || isStreaming || creatingWorkflow || routing}
                    />
                  )}
                  {onRoutingModeChange && (
                    <Segmented
                      size="small"
                      value={routingMode}
                      className={styles.routingSegment}
                      options={[
                        { label: '自动', value: 'auto' },
                        { label: '对话', value: 'chat' },
                        { label: 'Agent', value: 'agent' },
                      ]}
                      onChange={(mode) => onRoutingModeChange(mode as 'auto' | 'chat' | 'agent')}
                      disabled={loading || isStreaming || creatingWorkflow || routing}
                    />
                  )}
                  {workflowTemplateOptions.length > 1 && (
                    <Select
                      size="small"
                      value={selectedWorkflowTemplate}
                      options={workflowTemplateOptions}
                      onChange={onWorkflowTemplateChange}
                      style={{ minWidth: 128 }}
                      disabled={loading || isStreaming || creatingWorkflow || routing}
                    />
                  )}
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
                    {routing ? '判断中' : routingMode === 'agent' ? '启动' : '发送'}
                  </Button>
                </motion.div>
              )}
            </div>
          </div>
        </motion.div>

        <div className={styles.hint}>
          <Text type="secondary" style={{ fontSize: 11 }}>
            按 Enter 发送 · Shift+Enter 换行 · 开发/修改/测试类目标会自动进入 Agent 工作
          </Text>
        </div>
      </div>
    </motion.div>
  );
};

export default ChatInput;
