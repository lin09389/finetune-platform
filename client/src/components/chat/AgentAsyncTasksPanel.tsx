import {
  CloseCircleOutlined,
  EyeOutlined,
  HistoryOutlined,
  PlusOutlined,
  ReloadOutlined,
  RetweetOutlined,
} from '@ant-design/icons';
import { Button, Drawer, Empty, Input, Modal, Select, Space, Tag, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';
import {
  listAgentAsyncTaskEvents,
  type AgentAsyncTask,
  type AgentAsyncTaskEvent,
  type AgentAsyncTaskMetrics,
} from '../../services/api';
import { notify } from '../../utils/notify';
import { AgentChildSessionDetail } from './AgentChildSessionDrawer';
import styles from './AgentAsyncTasksPanel.module.css';

const statusOptions = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: '等待' },
  { value: 'running', label: '运行中' },
  { value: 'completed', label: '完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
];

const agentOptions = [
  { value: 'explore', label: 'Explore' },
  { value: 'review', label: 'Review' },
];

const statusColor: Record<string, string> = {
  pending: 'gold',
  running: 'processing',
  completed: 'success',
  failed: 'error',
  cancelled: 'default',
};

const statusLabel: Record<string, string> = {
  pending: '等待',
  running: '运行中',
  completed: '完成',
  failed: '失败',
  cancelled: '已取消',
};

const healthColor: Record<string, string> = {
  ok: 'success',
  waiting: 'processing',
  attention: 'warning',
  failed: 'error',
  cancelled: 'default',
};

const healthLabel: Record<string, string> = {
  ok: '健康',
  waiting: '等待',
  attention: '关注',
  failed: '失败',
  cancelled: '取消',
};

function formatDuration(ms?: number | null) {
  if (ms === undefined || ms === null) return '';
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

interface AgentAsyncTasksPanelProps {
  sessionId?: string | null;
  tasks: AgentAsyncTask[];
  metrics: AgentAsyncTaskMetrics | null;
  loading: boolean;
  statusFilter: string;
  focusedTaskId?: string | null;
  expandedTaskId?: string | null;
  onStatusFilterChange: (filter: string) => void;
  onExpandedTaskChange?: (taskId: string | null) => void;
  onRefresh: () => void | Promise<void>;
  onStartTask: (payload: { subagent_type: string; description: string }) => void | Promise<void>;
  onCancelTask: (taskId: string, payload?: { reason?: string }) => void | Promise<void>;
  onRestartTask: (taskId: string, payload: { description: string }) => void | Promise<void>;
}

export default function AgentAsyncTasksPanel({
  sessionId,
  tasks,
  metrics,
  loading,
  statusFilter,
  focusedTaskId,
  expandedTaskId,
  onStatusFilterChange,
  onExpandedTaskChange,
  onRefresh,
  onStartTask,
  onCancelTask,
  onRestartTask,
}: AgentAsyncTasksPanelProps) {
  const [subagentType, setSubagentType] = useState('explore');
  const [description, setDescription] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [activeTask, setActiveTask] = useState<AgentAsyncTask | null>(null);
  const [restartDescription, setRestartDescription] = useState('');
  const [localExpandedTaskId, setLocalExpandedTaskId] = useState<string | null>(null);
  const [eventsOpen, setEventsOpen] = useState(false);
  const [taskEvents, setTaskEvents] = useState<AgentAsyncTaskEvent[]>([]);
  const [eventsTask, setEventsTask] = useState<AgentAsyncTask | null>(null);
  const taskRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const isExpandedControlled = expandedTaskId !== undefined;
  const currentExpandedTaskId = isExpandedControlled ? expandedTaskId : localExpandedTaskId;
  const setExpandedTaskId = onExpandedTaskChange ?? setLocalExpandedTaskId;

  const canCreate = Boolean(sessionId && description.trim());

  useEffect(() => {
    if (!focusedTaskId) return;
    const node = taskRefs.current[focusedTaskId];
    node?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
    if (tasks.some((task) => task.task_id === focusedTaskId)) {
      setExpandedTaskId(focusedTaskId);
    }
  }, [focusedTaskId, setExpandedTaskId, tasks]);

  const handleCreate = async () => {
    if (!sessionId || !canCreate) return;
    try {
      await onStartTask({ subagent_type: subagentType, description: description.trim() });
      setDescription('');
      setCreateOpen(false);
    } catch (error) {
      notify.error('异步子任务启动失败');
    }
  };

  const handleCancel = async (task: AgentAsyncTask) => {
    if (!sessionId) return;
    try {
      await onCancelTask(task.task_id, { reason: '用户在任务面板取消。' });
    } catch (error) {
      notify.error('异步子任务取消失败');
    }
  };

  const openRestart = (task: AgentAsyncTask) => {
    setActiveTask(task);
    setRestartDescription(String(task.input?.description || ''));
  };

  const handleRestart = async () => {
    if (!sessionId || !activeTask || !restartDescription.trim()) return;
    try {
      await onRestartTask(activeTask.task_id, { description: restartDescription.trim() });
      setActiveTask(null);
      setRestartDescription('');
    } catch (error) {
      notify.error('异步子任务重启失败');
    }
  };

  const toggleChildSession = (task: AgentAsyncTask) => {
    if (!task.child_session_id) return;
    setExpandedTaskId(currentExpandedTaskId === task.task_id ? null : task.task_id);
  };

  const openTaskEvents = async (task: AgentAsyncTask) => {
    if (!sessionId) return;
    setEventsTask(task);
    setEventsOpen(true);
    setTaskEvents([]);
    try {
      setTaskEvents(await listAgentAsyncTaskEvents(sessionId, task.task_id, 100));
    } catch (error) {
      notify.error('子任务事件加载失败');
    }
  };

  if (!sessionId) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Agent 会话" />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.toolbar}>
        <Select
          className={styles.toolbarSelect}
          value={statusFilter}
          options={statusOptions}
          onChange={onStatusFilterChange}
        />
        <Button icon={<PlusOutlined />} onClick={() => setCreateOpen((value) => !value)}>
          新建子任务
        </Button>
        <Button aria-label="刷新异步子任务" icon={<ReloadOutlined />} loading={loading} onClick={() => void onRefresh()} />
      </div>

      {createOpen ? (
        <div className={styles.createForm}>
          <Space.Compact block>
            <Select value={subagentType} options={agentOptions} onChange={setSubagentType} style={{ width: 112 }} />
            <Button type="primary" icon={<PlusOutlined />} disabled={!canCreate} loading={loading} onClick={handleCreate}>
              创建
            </Button>
          </Space.Compact>
          <Input.TextArea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            placeholder="输入子任务目标"
          />
        </div>
      ) : null}

      <div className={styles.metricsRow}>
        <div><strong>{metrics?.total ?? tasks.length}</strong><span>总数</span></div>
        <div><strong>{metrics?.running ?? 0}</strong><span>运行</span></div>
        <div><strong>{metrics?.failed ?? 0}</strong><span>失败</span></div>
        <div><strong>{metrics?.attention ?? 0}</strong><span>关注</span></div>
        <div><strong>{metrics?.recovery_count ?? 0}</strong><span>恢复</span></div>
      </div>

      <div className={styles.taskList}>
        {tasks.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无异步子任务" />
        ) : tasks.map((task) => {
          const isExpanded = currentExpandedTaskId === task.task_id;
          return (
          <div
            key={task.task_id}
            ref={(node) => { taskRefs.current[task.task_id] = node; }}
            className={`${styles.taskItem} ${focusedTaskId === task.task_id ? styles.taskItemFocused : ''} ${isExpanded ? styles.taskItemExpanded : ''}`}
            data-focused={focusedTaskId === task.task_id ? 'true' : undefined}
          >
            <div className={styles.taskHeader}>
              <Typography.Text strong className={styles.taskTitle} ellipsis>
                {task.agent_name}
              </Typography.Text>
              <Tag color={statusColor[task.status] || 'default'}>{statusLabel[task.status] || task.status}</Tag>
              <Tag color={healthColor[task.health_status || 'waiting'] || 'default'}>
                {healthLabel[task.health_status || 'waiting'] || task.health_status}
              </Tag>
            </div>
            <div className={styles.taskDescription}>{String(task.input?.description || task.result?.summary || '')}</div>
            <div className={styles.taskMeta}>
              <span>{task.task_id}</span>
              {task.restart_count > 0 ? <span>重启 {task.restart_count}</span> : null}
              {task.duration_ms !== undefined && task.duration_ms !== null ? <span>耗时 {formatDuration(task.duration_ms)}</span> : null}
              {task.queue_wait_ms !== undefined && task.queue_wait_ms !== null ? <span>等待 {formatDuration(task.queue_wait_ms)}</span> : null}
              {task.diagnostics?.last_event_type ? <span>事件 {String(task.diagnostics.last_event_type)}</span> : null}
            </div>
            {Array.isArray(task.diagnostics?.warnings) && task.diagnostics.warnings.length > 0 ? (
              <div className={styles.warningText}>{String(task.diagnostics.warnings[0])}</div>
            ) : null}
            <div className={styles.taskActions}>
              <Button size="small" icon={<ReloadOutlined />} onClick={() => void onRefresh()}>刷新</Button>
              {task.child_session_id ? (
                <Button size="small" icon={<EyeOutlined />} type={isExpanded ? 'primary' : 'default'} onClick={() => toggleChildSession(task)}>
                  {isExpanded ? '收起详情' : '展开详情'}
                </Button>
              ) : null}
              <Button size="small" icon={<HistoryOutlined />} onClick={() => openTaskEvents(task)}>事件</Button>
              {['pending', 'running'].includes(task.status) ? (
                <Button size="small" danger icon={<CloseCircleOutlined />} onClick={() => handleCancel(task)}>取消</Button>
              ) : null}
              <Button size="small" icon={<RetweetOutlined />} onClick={() => openRestart(task)}>重启</Button>
            </div>
            {isExpanded && task.child_session_id ? (
              <div className={styles.inlineDetail}>
                <div className={styles.inlineDetailHeader}>
                  <Typography.Text strong>子会话详情</Typography.Text>
                  <div className={styles.taskMeta}>
                    <span>Agent {task.agent_name}</span>
                    <span>状态 {statusLabel[task.status] || task.status}</span>
                    <span>任务 {task.task_id}</span>
                    <span>子会话 {task.child_session_id}</span>
                  </div>
                </div>
                <AgentChildSessionDetail childSessionId={task.child_session_id} onDecisionSubmitted={onRefresh} />
              </div>
            ) : null}
          </div>
        );
        })}
      </div>

      <Modal
        title="重启异步子任务"
        open={Boolean(activeTask)}
        onCancel={() => setActiveTask(null)}
        onOk={handleRestart}
        okButtonProps={{ disabled: !restartDescription.trim(), loading }}
        destroyOnHidden
      >
        <div className={styles.restartForm}>
          <Typography.Text code>{activeTask?.task_id}</Typography.Text>
          <Input.TextArea
            rows={4}
            value={restartDescription}
            onChange={(event) => setRestartDescription(event.target.value)}
          />
        </div>
      </Modal>

      <Drawer
        title={`子任务事件${eventsTask ? ` · ${eventsTask.agent_name}` : ''}`}
        width={520}
        open={eventsOpen}
        onClose={() => setEventsOpen(false)}
        destroyOnHidden
      >
        <div className={styles.eventList}>
          {taskEvents.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : taskEvents.map((event) => (
            <div key={event.id} className={styles.eventItem}>
              <div className={styles.eventHeader}>
                <Typography.Text strong>{event.event_type}</Typography.Text>
                <Tag>{event.status || 'event'}</Tag>
              </div>
              <div className={styles.taskDescription}>{event.message}</div>
              <div className={styles.taskMeta}>
                <span>{event.created_at}</span>
                {event.child_session_id ? <span>{event.child_session_id}</span> : null}
              </div>
            </div>
          ))}
        </div>
      </Drawer>
    </div>
  );
}
