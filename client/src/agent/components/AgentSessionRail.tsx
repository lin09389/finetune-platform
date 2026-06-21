import { PlusOutlined, PushpinFilled, PushpinOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Input, Segmented, Tooltip } from 'antd';
import { useDeferredValue, useMemo, useState } from 'react';
import type { RecentAgentSession } from '../runtime/agentRuntime';
import styles from '../workbench/AgentWorkbench.module.css';

const PINNED_SESSIONS_KEY = 'finetune.agent.pinned-sessions.v1';

const STATUS_LABELS: Record<string, string> = {
  idle: '待命',
  running: '运行中',
  waiting_permission: '等待审批',
  waiting_approval: '等待审批',
  verifying: '验证中',
  repairing: '修复中',
  completed: '已完成',
  failed: '失败',
  interrupted: '已停止',
  needs_manual_review: '需复核',
};

interface AgentSessionRailProps {
  sessions: RecentAgentSession[];
  activeSessionId: string | null;
  onNew: () => void;
  onSelect: (sessionId: string) => void;
  embedded?: boolean;
}

export default function AgentSessionRail({
  sessions,
  activeSessionId,
  onNew,
  onSelect,
  embedded = false,
}: AgentSessionRailProps) {
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<'all' | 'active' | 'done'>('all');
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => {
    if (typeof localStorage === 'undefined') return [];
    try {
      const value = JSON.parse(localStorage.getItem(PINNED_SESSIONS_KEY) || '[]');
      return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
    } catch {
      return [];
    }
  });
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const visibleSessions = useMemo(() => sessions
    .filter((session) => {
      if (scope === 'active' && ![
        'running',
        'waiting_permission',
        'waiting_approval',
        'verifying',
        'repairing',
      ].includes(session.status)) return false;
      if (scope === 'done' && !['completed', 'failed', 'interrupted'].includes(session.status)) return false;
      return !deferredQuery
        || session.title.toLowerCase().includes(deferredQuery)
        || session.projectPath?.toLowerCase().includes(deferredQuery);
    })
    .sort((left, right) => {
      const pinDelta = Number(pinnedIds.includes(right.id)) - Number(pinnedIds.includes(left.id));
      return pinDelta || right.updatedAt.localeCompare(left.updatedAt);
    }), [deferredQuery, pinnedIds, scope, sessions]);

  const togglePin = (sessionId: string) => {
    setPinnedIds((current) => {
      const next = current.includes(sessionId)
        ? current.filter((id) => id !== sessionId)
        : [sessionId, ...current].slice(0, 20);
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(PINNED_SESSIONS_KEY, JSON.stringify(next));
      }
      return next;
    });
  };

  return (
    <aside
      className={`${styles.sessionRail} ${embedded ? styles.embeddedRail : ''}`}
      aria-label="Agent 会话"
    >
      <Button className={styles.newTask} icon={<PlusOutlined />} aria-label="新建任务" onClick={onNew}>
        新建任务
      </Button>
      <Input
        className={styles.sessionSearch}
        size="small"
        allowClear
        prefix={<SearchOutlined />}
        value={query}
        placeholder="搜索会话"
        aria-label="搜索 Agent 会话"
        onChange={(event) => setQuery(event.target.value)}
      />
      <Segmented
        className={styles.sessionScope}
        block
        size="small"
        value={scope}
        onChange={(value) => setScope(value as typeof scope)}
        options={[
          { value: 'all', label: '全部' },
          { value: 'active', label: '进行中' },
          { value: 'done', label: '已结束' },
        ]}
      />
      <div className={styles.railSection}>
        <span className={styles.railLabel}>最近运行 · {visibleSessions.length}</span>
        {visibleSessions.length === 0 ? (
          <div className={styles.railEmpty}>{sessions.length ? '没有匹配的会话' : '暂无运行'}</div>
        ) : (
          <div className={styles.sessionList}>
            {visibleSessions.map((session) => (
              <div
                key={session.id}
                className={session.id === activeSessionId ? styles.sessionItemActive : styles.sessionItem}
              >
                <button type="button" className={styles.sessionSelect} onClick={() => onSelect(session.id)}>
                  <span className={styles.sessionTitle}>{session.title}</span>
                  <span className={styles.sessionMeta}>
                    <span className={`${styles.statusDot} ${styles[`status_${session.status}`] || ''}`} />
                    {STATUS_LABELS[session.status] || session.status}
                  </span>
                </button>
                <Tooltip title={pinnedIds.includes(session.id) ? '取消置顶' : '置顶'}>
                  <button
                    type="button"
                    className={styles.sessionPin}
                    aria-label={`${pinnedIds.includes(session.id) ? '取消置顶' : '置顶'} ${session.title}`}
                    aria-pressed={pinnedIds.includes(session.id)}
                    onClick={() => togglePin(session.id)}
                  >
                    {pinnedIds.includes(session.id) ? <PushpinFilled /> : <PushpinOutlined />}
                  </button>
                </Tooltip>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
