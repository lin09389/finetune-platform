import { ArrowUpOutlined, StopOutlined } from '@ant-design/icons';
import { Button, Input, Select, Tooltip } from 'antd';
import { useEffect, useRef, useState } from 'react';
import type { AgentInfo, AgentSession } from '../../services/api';
import styles from '../workbench/AgentWorkbench.module.css';

const { TextArea } = Input;

interface AgentTaskComposerProps {
  agents: AgentInfo[];
  session: AgentSession | null;
  busy: boolean;
  busyLabel?: string;
  submissionBlockedReason?: string;
  onSubmit: (content: string, agentId: string) => Promise<unknown>;
  onInterrupt: () => Promise<unknown>;
}

export default function AgentTaskComposer({
  agents,
  session,
  busy,
  busyLabel,
  submissionBlockedReason,
  onSubmit,
  onInterrupt,
}: AgentTaskComposerProps) {
  const [draft, setDraft] = useState('');
  const [agentId, setAgentId] = useState('build');
  const [submissionFailed, setSubmissionFailed] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const isRunning = Boolean(session && ['running', 'verifying', 'repairing', 'waiting_permission', 'waiting_approval'].includes(session.status));
  const isWaitingApproval = Boolean(session && ['waiting_permission', 'waiting_approval'].includes(session.status));
  const draftKey = `finetune.agent.draft.v1:${session?.id || 'new'}`;
  const draftKeyRef = useRef(draftKey);
  draftKeyRef.current = draftKey;

  useEffect(() => {
    if (session?.agent_id) setAgentId(session.agent_id);
  }, [session?.agent_id]);

  useEffect(() => {
    setDraft(sessionStorage.getItem(draftKey) || '');
  }, [draftKey]);

  useEffect(() => {
    if (draft) sessionStorage.setItem(draftKey, draft);
    else sessionStorage.removeItem(draftKey);
  }, [draft, draftKey]);

  useEffect(() => {
    const focusComposer = (event: KeyboardEvent) => {
      const target = event.target;
      const isEditing = target instanceof HTMLElement
        && target.matches('input, textarea, [contenteditable="true"]');
      if ((event.key === '/' && !isEditing) || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k')) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', focusComposer);
    return () => window.removeEventListener('keydown', focusComposer);
  }, []);

  const submit = async () => {
    if (!draft.trim() || busy) return;
    const content = draft;
    const submittedDraftKey = draftKey;
    setSubmissionFailed(false);
    setDraft('');
    sessionStorage.removeItem(draftKey);
    try {
      await onSubmit(content, agentId);
    } catch {
      sessionStorage.setItem(submittedDraftKey, content);
      if (draftKeyRef.current === submittedDraftKey) {
        setSubmissionFailed(true);
        setDraft(content);
      }
    }
  };

  return (
    <div className={styles.composer}>
      <TextArea
        ref={inputRef}
        value={draft}
        onChange={(event) => {
          setSubmissionFailed(false);
          setDraft(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void submit();
          }
        }}
        placeholder={session ? (isRunning ? '补充说明或追加要求，Agent 会结合当前上下文处理' : '继续描述任务或补充要求') : '输入任务目标'}
        autoSize={{ minRows: 3, maxRows: 8 }}
        aria-label="任务目标"
      />
      <div className={styles.composerFooter}>
        <div className={styles.composerOptions}>
          <Select
            variant="borderless"
            size="small"
            value={agentId}
            disabled={Boolean(session)}
            aria-label="选择 Agent"
            onChange={setAgentId}
            options={(agents.length > 0 ? agents : [{ id: 'build', name: '构建 Agent' }]).map((agent) => ({
              value: agent.id,
              label: agent.name,
            }))}
          />
          <span aria-live="polite">
            {submissionBlockedReason && !session
              ? submissionBlockedReason
              : isWaitingApproval
              ? 'Agent 暂停，等待你审批工具执行'
              : busy
                ? busyLabel
                : isRunning
                  ? '输入内容可追加到当前任务 · Enter 发送'
                  : submissionFailed
                    ? '提交失败，内容已恢复，可再次发送'
                    : 'Enter 发送 · Shift+Enter 换行'}
          </span>
        </div>
        {isRunning ? (
          <Tooltip title="停止当前运行">
            <Button
              danger
              shape="circle"
              icon={<StopOutlined />}
              loading={busy}
              onClick={() => void onInterrupt()}
              aria-label="停止运行"
            />
          </Tooltip>
        ) : null}
        <Tooltip title={submissionBlockedReason && !session ? submissionBlockedReason : (isRunning ? '追加消息到当前任务' : '提交任务')}>
          <Button
            type="primary"
            shape="circle"
            icon={<ArrowUpOutlined />}
            disabled={!draft.trim() || busy || Boolean(submissionBlockedReason && !session)}
            loading={busy}
            onClick={() => void submit()}
            aria-label={isRunning ? '追加消息' : '提交任务'}
          />
        </Tooltip>
      </div>
    </div>
  );
}
