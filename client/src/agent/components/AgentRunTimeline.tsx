import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  LoadingOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Empty } from 'antd';
import ReactMarkdown from 'react-markdown';
import { Virtuoso } from 'react-virtuoso';
import type { AgentSessionUiTimelineItem } from '../../services/api';
import styles from '../workbench/AgentWorkbench.module.css';

function itemIcon(item: AgentSessionUiTimelineItem) {
  if (item.status === 'running' || item.status === 'pending') return <LoadingOutlined spin />;
  if (item.status === 'failed' || item.status === 'blocked') return <ExclamationCircleOutlined />;
  if (item.type === 'permission') return <SafetyCertificateOutlined />;
  if (item.type === 'tool_call' || item.type === 'tool_result') return <ToolOutlined />;
  if (item.type === 'command') return <CodeOutlined />;
  if (item.type === 'summary') return <FileTextOutlined />;
  if (item.status === 'completed' || item.status === 'approved' || item.status === 'executed') {
    return <CheckCircleOutlined />;
  }
  return <ClockCircleOutlined />;
}

function itemTitle(item: AgentSessionUiTimelineItem) {
  return item.title || item.tool || ({
    text: 'Agent 输出',
    tool_call: '工具调用',
    tool_result: '工具结果',
    command: '命令',
    permission: '等待审批',
    summary: '运行总结',
    error: '执行错误',
    diff: '文件变更',
  }[item.type] || item.type);
}

interface AgentRunTimelineProps {
  timeline: AgentSessionUiTimelineItem[];
}

export default function AgentRunTimeline({ timeline }: AgentRunTimelineProps) {
  if (timeline.length === 0) {
    return (
      <div className={styles.timelineEmpty}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="提交任务后，执行过程会显示在这里" />
      </div>
    );
  }

  return (
    <div className={styles.timeline} aria-label="Agent 执行时间线">
      <Virtuoso
        data={timeline}
        followOutput="smooth"
        initialTopMostItemIndex={Math.max(0, timeline.length - 1)}
        itemContent={(_, item) => (
          <article className={`${styles.timelineItem} ${styles[`timeline_${item.status || 'default'}`] || ''}`}>
            <div className={styles.timelineIcon}>{itemIcon(item)}</div>
            <div className={styles.timelineBody}>
              <div className={styles.timelineHeading}>
                <strong>{itemTitle(item)}</strong>
                <span>{item.status || item.type}</span>
              </div>
              {item.content ? (
                <div className={styles.timelineContent}>
                  <ReactMarkdown>{item.content}</ReactMarkdown>
                </div>
              ) : null}
              {!item.content && item.payload ? (
                <pre className={styles.timelinePayload}>{JSON.stringify(item.payload, null, 2)}</pre>
              ) : null}
            </div>
          </article>
        )}
      />
    </div>
  );
}
