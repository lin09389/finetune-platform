import {
  CloseCircleOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  RetweetOutlined,
} from '@ant-design/icons';
import { Button, Drawer, Empty, Input, Modal, Select, Space, Tag, Typography } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import {
  cancelAgentAsyncTask,
  getAgentSession,
  listAgentAsyncTasks,
  startAgentAsyncTask,
  updateAgentAsyncTask,
  type AgentAsyncTask,
  type AgentSession,
} from '../../services/api';
import { notify } from '../../utils/notify';
import AgentSessionTimeline from './AgentSessionTimeline';
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

interface AgentAsyncTasksPanelProps {
  sessionId?: string | null;
  refreshKey?: string | number;
}

export default function AgentAsyncTasksPanel({ sessionId, refreshKey }: AgentAsyncTasksPanelProps) {
  const [statusFilter, setStatusFilter] = useState('all');
  const [tasks, setTasks] = useState<AgentAsyncTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [subagentType, setSubagentType] = useState('explore');
  const [description, setDescription] = useState('');
  const [activeTask, setActiveTask] = useState<AgentAsyncTask | null>(null);
  const [restartDescription, setRestartDescription] = useState('');
  const [childSession, setChildSession] = useState<AgentSession | null>(null);
  const [childOpen, setChildOpen] = useState(false);

  const canCreate = Boolean(sessionId && description.trim());

  const loadTasks = useCallback(async () => {
    if (!sessionId) {
      setTasks([]);
      return;
    }
    setLoading(true);
    try {
      const response = await listAgentAsyncTasks(sessionId, statusFilter);
      setTasks(response.tasks);
    } catch (error) {
      notify.error('异步子任务加载失败');
    } finally {
      setLoading(false);
    }
  }, [sessionId, statusFilter]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks, refreshKey]);

  const handleCreate = async () => {
    if (!sessionId || !canCreate) return;
    setLoading(true);
    try {
      await startAgentAsyncTask(sessionId, { subagent_type: subagentType, description: description.trim() });
      setDescription('');
      await loadTasks();
    } catch (error) {
      notify.error('异步子任务启动失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async (task: AgentAsyncTask) => {
    if (!sessionId) return;
    setLoading(true);
    try {
      await cancelAgentAsyncTask(sessionId, task.task_id, { reason: '用户在任务面板取消。' });
      await loadTasks();
    } catch (error) {
      notify.error('异步子任务取消失败');
    } finally {
      setLoading(false);
    }
  };

  const openRestart = (task: AgentAsyncTask) => {
    setActiveTask(task);
    setRestartDescription(String(task.input?.description || ''));
  };

  const handleRestart = async () => {
    if (!sessionId || !activeTask || !restartDescription.trim()) return;
    setLoading(true);
    try {
      await updateAgentAsyncTask(sessionId, activeTask.task_id, { description: restartDescription.trim() });
      setActiveTask(null);
      setRestartDescription('');
      await loadTasks();
    } catch (error) {
      notify.error('异步子任务重启失败');
    } finally {
      setLoading(false);
    }
  };

  const openChildSession = async (task: AgentAsyncTask) => {
    if (!task.child_session_id) return;
    setChildOpen(true);
    setChildSession(null);
    try {
      setChildSession(await getAgentSession(task.child_session_id));
    } catch (error) {
      notify.error('子会话加载失败');
    }
  };

  if (!sessionId) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Agent 会话" />;
  }

  return (
    <div className={styles.panel}>
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

      <div className={styles.toolbar}>
        <Select
          className={styles.toolbarSelect}
          value={statusFilter}
          options={statusOptions}
          onChange={setStatusFilter}
        />
        <Button icon={<ReloadOutlined />} loading={loading} onClick={loadTasks} />
      </div>

      <div className={styles.taskList}>
        {tasks.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无异步子任务" />
        ) : tasks.map((task) => (
          <div key={task.task_id} className={styles.taskItem}>
            <div className={styles.taskHeader}>
              <Typography.Text strong className={styles.taskTitle} ellipsis>
                {task.agent_name}
              </Typography.Text>
              <Tag color={statusColor[task.status] || 'default'}>{statusLabel[task.status] || task.status}</Tag>
            </div>
            <div className={styles.taskDescription}>{String(task.input?.description || task.result?.summary || '')}</div>
            <div className={styles.taskMeta}>
              <span>{task.task_id}</span>
              {task.restart_count > 0 ? <span>重启 {task.restart_count}</span> : null}
            </div>
            <div className={styles.taskActions}>
              <Button size="small" icon={<ReloadOutlined />} onClick={loadTasks}>刷新</Button>
              {task.child_session_id ? (
                <Button size="small" icon={<EyeOutlined />} onClick={() => openChildSession(task)}>详情</Button>
              ) : null}
              {['pending', 'running'].includes(task.status) ? (
                <Button size="small" danger icon={<CloseCircleOutlined />} onClick={() => handleCancel(task)}>取消</Button>
              ) : null}
              <Button size="small" icon={<RetweetOutlined />} onClick={() => openRestart(task)}>重启</Button>
            </div>
          </div>
        ))}
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
        title="子会话详情"
        width={560}
        open={childOpen}
        onClose={() => setChildOpen(false)}
        destroyOnHidden
      >
        <div className={styles.drawerBody}>
          {childSession ? <AgentSessionTimeline session={childSession} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </div>
      </Drawer>
    </div>
  );
}
