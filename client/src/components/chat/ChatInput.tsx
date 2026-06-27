import {
  AudioOutlined,
  ClearOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Button, Input, Tooltip, Typography, message } from 'antd';
import type { TextAreaRef } from 'antd/es/input/TextArea';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useResponsive } from '../../hooks/useResponsive';
import { searchContextMentions } from '../../services/api';
import type { ActiveFileContext, ExplicitContextMention, WorkspaceTreeNode } from '../../services/api';
import styles from './ChatInput.module.css';

const { TextArea } = Input;
const { Text } = Typography;

interface ChatInputProps {
  onSend: (content: string) => void;
  onStop?: () => void;
  onClear?: () => void;
  onNewChat?: () => void;
  disabled?: boolean;
  loading?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  modelId?: string;
  maxLength?: number;
  showModelInfo?: boolean;
  agentModeAvailable?: boolean;
  routingMode?: 'auto' | 'chat' | 'agent';
  routing?: boolean;
  autonomyMode?: 'none' | 'semi' | 'full' | 'safe_auto' | 'confirm_all' | 'read_only';
  workspaceFiles?: WorkspaceTreeNode[];
  projectPath?: string;
  selectedMentions?: ExplicitContextMention[];
  onMentionsChange?: (mentions: ExplicitContextMention[]) => void;
  activeFileContext?: ActiveFileContext | null;
}

interface MentionSuggestion extends ExplicitContextMention {
  detail?: string;
}

type SpeechRecognitionConstructor = new () => {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
};

type SpeechRecognitionResultEventLike = {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
};

type SpeechRecognitionWindow = Window & {
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
  SpeechRecognition?: SpeechRecognitionConstructor;
};

const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  onStop,
  onClear,
  onNewChat,
  disabled = false,
  loading = false,
  isStreaming = false,
  placeholder = '有问题，尽管问',
  modelId,
  maxLength = 4000,
  showModelInfo = true,
  routingMode = 'auto',
  routing = false,
  workspaceFiles = [],
  projectPath,
  selectedMentions = [],
  onMentionsChange,
  activeFileContext,
}) => {
  const { isMobile } = useResponsive();
  const [value, setValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<TextAreaRef | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [cursorIndex, setCursorIndex] = useState(0);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [semanticSuggestions, setSemanticSuggestions] = useState<MentionSuggestion[]>([]);
  const [activeSuggestion, setActiveSuggestion] = useState(0);

  const canSend = value.trim().length > 0 && !loading;
  const getTextareaElement = useCallback((): HTMLTextAreaElement | null => {
    return textareaRef.current?.resizableTextArea?.textArea || null;
  }, []);

  const localFileSuggestions = useMemo<MentionSuggestion[]>(() => {
    const query = (mentionQuery || '').toLowerCase();
    return workspaceFiles
      .filter((node) => node.kind === 'file')
      .filter((node) => {
        if (!query) return true;
        return node.name.toLowerCase().includes(query) || node.path.toLowerCase().includes(query);
      })
      .slice(0, 12)
      .map((node) => ({
        id: `file:${node.path}`,
        type: 'file',
        label: node.name,
        path: node.path,
        source: 'workspace',
        detail: node.path,
      }));
  }, [mentionQuery, workspaceFiles]);

  const mentionSuggestions = useMemo(() => {
    const seen = new Set<string>();
    return [...localFileSuggestions, ...semanticSuggestions]
      .filter((item) => {
        const key = item.id || `${item.type}:${item.path}:${item.label}:${item.line || ''}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 10);
  }, [localFileSuggestions, semanticSuggestions]);

  const updateMentionQuery = useCallback((nextValue: string, nextCursor: number) => {
    setCursorIndex(nextCursor);
    const beforeCursor = nextValue.slice(0, nextCursor);
    const match = beforeCursor.match(/(?:^|\s)@([\w./\\:-]*)$/);
    setMentionQuery(match ? match[1] || '' : null);
  }, []);

  useEffect(() => {
    if (mentionQuery === null || !projectPath) {
      setSemanticSuggestions([]);
      return;
    }
    const query = mentionQuery.trim();
    if (query.length < 2) {
      setSemanticSuggestions([]);
      return;
    }
    const timeout = setTimeout(() => {
      searchContextMentions({ query, project_path: projectPath, limit: 10 })
        .then((result) => {
          if (!result.success) {
            setSemanticSuggestions([]);
            return;
          }
          setSemanticSuggestions((result.mentions || []).map((item) => ({
            ...item,
            source: item.source || 'semantic',
            detail: item.detail || item.path,
          })));
        })
        .catch(() => setSemanticSuggestions([]));
    }, 180);
    return () => clearTimeout(timeout);
  }, [mentionQuery, projectPath]);

  useEffect(() => {
    setActiveSuggestion(0);
  }, [mentionQuery, mentionSuggestions.length]);

  const handleSend = useCallback(async () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue('');
    setMentionQuery(null);
    onMentionsChange?.([]);
  }, [canSend, onMentionsChange, onSend, value]);

  const insertMention = useCallback((suggestion: MentionSuggestion) => {
    const textarea = getTextareaElement();
    const cursor = textarea?.selectionStart ?? cursorIndex;
    const beforeCursor = value.slice(0, cursor);
    const match = beforeCursor.match(/(?:^|\s)@([\w./\\:-]*)$/);
    const start = match ? cursor - (match[1]?.length || 0) - 1 : cursor;
    const token = `@${suggestion.label}`;
    const nextValue = `${value.slice(0, start)}${token} ${value.slice(cursor)}`;
    setValue(nextValue);
    setMentionQuery(null);
    onMentionsChange?.(
      selectedMentions.some((item) => item.id === suggestion.id)
        ? selectedMentions
        : [...selectedMentions, suggestion],
    );
    requestAnimationFrame(() => {
      const nextCursor = start + token.length + 1;
      textarea?.focus();
      textarea?.setSelectionRange(nextCursor, nextCursor);
      setCursorIndex(nextCursor);
    });
  }, [cursorIndex, getTextareaElement, onMentionsChange, selectedMentions, value]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (mentionQuery !== null && mentionSuggestions.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setActiveSuggestion((idx) => Math.min(idx + 1, mentionSuggestions.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setActiveSuggestion((idx) => Math.max(idx - 1, 0));
          return;
        }
        if (e.key === 'Tab') {
          e.preventDefault();
          const suggestion = mentionSuggestions[activeSuggestion] || mentionSuggestions[0];
          if (suggestion) insertMention(suggestion);
          return;
        }
        if (e.key === 'Escape') {
          setMentionQuery(null);
          return;
        }
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (mentionQuery !== null && mentionSuggestions.length > 0) {
          const suggestion = mentionSuggestions[activeSuggestion] || mentionSuggestions[0];
          if (suggestion) insertMention(suggestion);
          return;
        }
        if (isStreaming) {
          onStop?.();
        } else {
          handleSend();
        }
      }
    },
    [activeSuggestion, handleSend, insertMention, isStreaming, mentionQuery, mentionSuggestions, onStop],
  );

  const handleVoiceInput = useCallback(() => {
    const speechWindow = window as SpeechRecognitionWindow;
    if (!speechWindow.webkitSpeechRecognition && !speechWindow.SpeechRecognition) {
      message.warning('当前浏览器不支持语音输入');
      return;
    }

    const SpeechRecognition =
      speechWindow.webkitSpeechRecognition || speechWindow.SpeechRecognition;
    if (!SpeechRecognition) return;
    const recognition = new SpeechRecognition();

    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
      setIsRecording(true);
      message.info('开始录音...');
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript || '';
      setValue((prev) => prev + transcript);
    };

    recognition.onerror = () => {
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
            {routingMode !== 'chat' && (
              <Tooltip title={routingMode === 'agent' ? '强制 Agent 模式' : '自动路由模式'}>
                <div className={styles.modeIcon} data-mode={routingMode}>
                  <RobotOutlined />
                </div>
              </Tooltip>
            )}
            {routing && (
              <div className={styles.routingStatus}>
                <span className={styles.routingDot} />
                <span className={styles.routingText}>判断中...</span>
              </div>
            )}
            {!routing && onNewChat && (
              <Tooltip title="新对话">
                <Button 
                  type="text" 
                  icon={<PlusOutlined />} 
                  className={styles.iconBtn} 
                  onClick={onNewChat}
                />
              </Tooltip>
            )}
          </div>

          <div className={styles.inputAreaBody}>
            {(activeFileContext?.file_path || selectedMentions.length > 0) && (
              <div className={styles.contextChips} aria-label="已绑定上下文">
                {activeFileContext?.file_path && (
                  <span className={`${styles.contextChip} ${styles.contextChipPassive}`} title={activeFileContext.file_path}>
                    📄 {activeFileContext.file_path.split(/[\\/]/).pop()}
                    {activeFileContext.cursor ? `:${activeFileContext.cursor.line}` : ''}
                  </span>
                )}
                {selectedMentions.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={styles.contextChip}
                    onClick={() => onMentionsChange?.(selectedMentions.filter((mention) => mention.id !== item.id))}
                    title="移除此上下文"
                  >
                    📄 {item.label} <span className={styles.contextChipClose}>×</span>
                  </button>
                ))}
              </div>
            )}

            <TextArea
              ref={textareaRef}
              placeholder={placeholder}
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                updateMentionQuery(e.target.value, e.target.selectionStart ?? e.target.value.length);
              }}
              onKeyDown={handleKeyDown}
              onKeyUp={(e) => updateMentionQuery(e.currentTarget.value, e.currentTarget.selectionStart ?? e.currentTarget.value.length)}
              onClick={(e) => updateMentionQuery(e.currentTarget.value, e.currentTarget.selectionStart ?? e.currentTarget.value.length)}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              autoSize={{ minRows: 1, maxRows: 6 }}
              disabled={disabled || loading}
              maxLength={maxLength}
              variant="borderless"
              className={styles.textarea}
            />
          </div>

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

        {mentionQuery !== null && mentionSuggestions.length > 0 && (
          <div className={styles.mentionPanel} role="listbox" aria-label="上下文候选">
            {mentionSuggestions.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={`${styles.mentionItem} ${index === activeSuggestion ? styles.mentionItemActive : ''}`}
                onMouseDown={(event) => {
                  event.preventDefault();
                  insertMention(item);
                }}
                onMouseEnter={() => setActiveSuggestion(index)}
                role="option"
                aria-selected={index === activeSuggestion}
              >
                <span className={styles.mentionType}>{item.type === 'symbol' ? 'ƒ' : item.type === 'endpoint' ? 'API' : 'file'}</span>
                <span className={styles.mentionMain}>
                  <span className={styles.mentionLabel}>{item.label}</span>
                  {item.detail && <span className={styles.mentionDetail}>{item.detail}</span>}
                </span>
                {item.line && <span className={styles.mentionLine}>:{item.line}</span>}
              </button>
            ))}
          </div>
        )}
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
