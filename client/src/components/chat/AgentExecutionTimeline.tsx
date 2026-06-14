import { Empty, Tag, Typography } from 'antd';
import type { AgentExecutionTimelineItem } from '../../services/api';
import styles from './AgentWorkspacePanels.module.css';

interface AgentExecutionTimelineProps {
  items: AgentExecutionTimelineItem[];
  onSelectItem?: (item: AgentExecutionTimelineItem) => void;
}

const typeLabel: Record<AgentExecutionTimelineItem['type'], string> = {
  tool_call: '调用',
  tool_result: '结果',
  command: '命令',
  permission: '确认',
  summary: '摘要',
  error: '错误',
  recovery: '恢复',
};

const typeColor: Record<AgentExecutionTimelineItem['type'], string> = {
  tool_call: 'processing',
  tool_result: 'default',
  command: 'blue',
  permission: 'warning',
  summary: 'success',
  error: 'error',
  recovery: 'purple',
};

export default function AgentExecutionTimeline({ items, onSelectItem }: AgentExecutionTimelineProps) {
  if (!items.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行时间线" />;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <Typography.Text strong>Execution Console</Typography.Text>
          <Typography.Text type="secondary">工具调用、结果、确认与错误链路</Typography.Text>
        </div>
        <Tag>{items.length}</Tag>
      </div>
      <div className={styles.timelineList}>
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className={styles.timelineItem}
            onClick={() => onSelectItem?.(item)}
          >
            <span className={styles.timelineRail} data-type={item.type} />
            <div className={styles.timelineBody}>
              <div className={styles.timelineTitle}>
                <Typography.Text strong>{item.title}</Typography.Text>
                <Tag color={typeColor[item.type]}>{typeLabel[item.type]}</Tag>
                {item.status ? <Tag>{item.status}</Tag> : null}
              </div>
              {item.summary ? <Typography.Text type="secondary">{item.summary}</Typography.Text> : null}
              <div className={styles.metaRow}>
                <span>part {item.source_part_id}</span>
                {item.duration_ms != null ? <span>{item.duration_ms}ms</span> : null}
                {item.created_at ? <span>{item.created_at}</span> : null}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
