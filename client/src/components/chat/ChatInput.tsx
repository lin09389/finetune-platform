import {
  AudioOutlined,
  ClearOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Button, Input, Tooltip, Typography, message } from 'antd';
import React, { useCallback, useRef, useState } from 'react';
import { useResponsive } from '../../hooks/useResponsive';
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
  onCreateWorkflow?: (content: string) => Promise<void>;
  routingMode?: 'auto' | 'chat' | 'agent';
  routing?: boolean;
  autonomyMode?: 'none' | 'semi' | 'full' | 'safe_auto' | 'confirm_all' | 'read_only';
}

const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  onStop,
  onClear,
  disabled = false,
  loading = false,
  isStreaming = false,
  placeholder = '有问题，尽管问',
  modelId,
  maxLength = 4000,
  showModelInfo = true,
}) => {
  const { isMobile } = useResponsive();
  const [value, setValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isRecording, setIsRecording] = useState(false);

  const canSend = value.trim().length > 0 && !loading;

  const handleSend = useCallback(async () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue('');
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

  return (
    <div className={styles.inputShell}>
      <div className={styles.container}>
        <div className={`${styles.pillDock} ${isFocused ? styles.pillDockFocused : ''}`}>
          <div className={styles.leftActions}>
            <Tooltip title="更多功能">
              <Button 
                type="text" 
                icon={<PlusOutlined />} 
                className={styles.iconBtn} 
              />
            </Tooltip>
          </div>

          <TextArea
            ref={textareaRef}
            placeholder={placeholder}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={disabled || loading}
            maxLength={maxLength}
            variant="borderless"
            className={styles.textarea}
          />

          <div className={styles.rightActions}>
            {showModelInfo && modelId && !isMobile && (
              <div className={styles.modelBadge}>
                <RobotOutlined style={{ fontSize: 12, color: 'var(--accent-primary)' }} />
                <span className={styles.modelName}>{modelId}</span>
              </div>
            )}

            <Tooltip title="语音输入">
              <Button
                type="text"
                icon={<AudioOutlined />}
                onClick={handleVoiceInput}
                danger={isRecording}
                className={styles.iconBtn}
              />
            </Tooltip>

            {onClear && !isMobile && (
              <Tooltip title="清空对话">
                <Button
                  type="text"
                  icon={<ClearOutlined />}
                  onClick={onClear}
                  className={styles.iconBtn}
                />
              </Tooltip>
            )}

            {isStreaming ? (
              <Button
                type="primary"
                danger
                icon={<StopOutlined />}
                onClick={onStop}
                className={styles.sendBtnCircle}
              />
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined style={{ fontSize: 18, transform: 'translateX(1px)' }} />}
                onClick={handleSend}
                disabled={!canSend}
                className={styles.sendBtnCircle}
              />
            )}
          </div>
        </div>
      </div>

      <div className={styles.hint}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          按 Enter 发送 · Shift+Enter 换行
        </Text>
      </div>
    </div>
  );
};

export default ChatInput;
