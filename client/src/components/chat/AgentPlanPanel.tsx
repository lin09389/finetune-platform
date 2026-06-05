import { Empty, Progress, Tag, Typography } from 'antd';
import type { AgentTodoItem, AgentWorkspacePlan } from '../../services/api';
import styles from './AgentWorkspacePanels.module.css';

const statusLabel: Record<AgentTodoItem['status'], string> = {
  pending: '待处理',
  in_progress: '进行中',
  completed: '已完成',
  blocked: '阻塞',
};

const statusColor: Record<AgentTodoItem['status'], string> = {
  pending: 'default',
  in_progress: 'processing',
  completed: 'success',
  blocked: 'warning',
};

interface AgentPlanPanelProps {
  plan?: AgentWorkspacePlan | null;
}

export default function AgentPlanPanel({ plan }: AgentPlanPanelProps) {
  const todos = plan?.todos ?? [];
  const completed = todos.filter((todo) => todo.status === 'completed').length;
  const percent = todos.length ? Math.round((completed / todos.length) * 100) : 0;

  if (!todos.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Agent 计划" />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <Typography.Text strong>Agent Plan</Typography.Text>
          <Typography.Text type="secondary">来源：{plan?.source || 'workspace'}</Typography.Text>
        </div>
        <Tag color="processing">{completed}/{todos.length}</Tag>
      </div>
      <Progress percent={percent} size="small" />
      <div className={styles.todoList}>
        {todos.map((todo) => (
          <div key={todo.id} className={styles.todoItem} data-status={todo.status}>
            <div className={styles.todoMain}>
              <Typography.Text strong>{todo.title}</Typography.Text>
              {todo.summary ? <Typography.Text type="secondary">{todo.summary}</Typography.Text> : null}
              <div className={styles.metaRow}>
                <span>{todo.source}</span>
                {todo.owner_agent ? <span>{todo.owner_agent}</span> : null}
                {todo.linked_task_id ? <span>task {todo.linked_task_id}</span> : null}
              </div>
            </div>
            <Tag color={statusColor[todo.status]}>{statusLabel[todo.status]}</Tag>
          </div>
        ))}
      </div>
    </div>
  );
}
