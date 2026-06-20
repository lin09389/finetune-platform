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
  onSubmit: (content: string, agentId: string) => Promise<unknown>;
  onInterrupt: () => Promise<unknown>;
}

export default function AgentTaskComposer({
  agents,
  session,
  busy,
  busyLabel,
  onSubmit,
  onInterrupt,
}: AgentTaskComposerProps) {
  const [draft, setDraft] = useState('');
  const [agentId, setAgentId] = useState('build');
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const isRunning = Boolean(session && ['running', 'verifying', 'repairing'].includes(session.status));

  useEffect(() => {
    if (session?.agent_id) setAgentId(session.agent_id);
  }, [session?.agent_id]);

  const submit = async () => {
    if (!draft.trim() || busy) return;
    const content = draft;
    setDraft('');
    try {
      await onSubmit(content, agentId);
    } catch {
      setDraft(content);
    }
  };

  return (
    <div className={styles.composer}>
      <TextArea
        ref={inputRef}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            void submit();
          }
        }}
        placeholder={session ? '继续描述任务或补充要求' : '输入任务目标'}
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
            options={(agents.length > 0 ? agents : [{ id: 'build', name: 'Build Agent' }]).map((agent) => ({
              value: agent.id,
              label: agent.name,
            }))}
          />
          <span>{busy ? busyLabel : 'Enter 发送 · Shift+Enter 换行'}</span>
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
        ) : (
          <Button
            type="primary"
            shape="circle"
            icon={<ArrowUpOutlined />}
            disabled={!draft.trim() || busy}
            loading={busy}
            onClick={() => void submit()}
            aria-label="提交任务"
          />
        )}
      </div>
    </div>
  );
}
