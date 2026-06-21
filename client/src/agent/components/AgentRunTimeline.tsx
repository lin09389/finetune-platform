import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  LoadingOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
  DownOutlined,
  UpOutlined,
} from '@ant-design/icons';
import { Button, Empty, Input, Segmented, Switch } from 'antd';
import ReactMarkdown from 'react-markdown';
import { Virtuoso } from 'react-virtuoso';
import { useDeferredValue, useMemo, useState } from 'react';
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

export function TimelineContent({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const collapsible = content.length > 600 || content.split('\n').length > 10;
  return (
    <>
      <div className={`${styles.timelineContent} ${collapsible && !expanded ? styles.timelineContentCollapsed : ''}`}>
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
      {collapsible ? (
        <Button
          className={styles.timelineExpand}
          type="link"
          size="small"
          icon={expanded ? <UpOutlined /> : <DownOutlined />}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? '收起' : '展开'}
        </Button>
      ) : null}
    </>
  );
}

export default function AgentRunTimeline({ timeline }: AgentRunTimelineProps) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'output' | 'tools' | 'issues'>('all');
  const [autoFollow, setAutoFollow] = useState(true);
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const visibleTimeline = useMemo(() => timeline.filter((item) => {
    if (filter === 'output' && !['text', 'summary'].includes(item.type)) return false;
    if (filter === 'tools' && !['tool_call', 'tool_result', 'command', 'diff'].includes(item.type)) return false;
    if (filter === 'issues' && !['failed', 'blocked'].includes(item.status || '') && item.type !== 'error' && item.type !== 'permission') {
      return false;
    }
    if (!deferredQuery) return true;
    const haystack = [
      itemTitle(item),
      item.content,
      item.tool,
      JSON.stringify(item.payload || {}),
    ].join(' ').toLowerCase();
    return haystack.includes(deferredQuery);
  }), [deferredQuery, filter, timeline]);

  if (timeline.length === 0) {
    return (
      <div className={styles.timelineEmpty}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="提交任务后，执行过程会显示在这里" />
      </div>
    );
  }

  return (
    <div className={styles.timeline} aria-label="Agent 执行时间线">
      <div className={styles.timelineToolbar}>
        <Input.Search
          allowClear
          size="small"
          value={query}
          placeholder="搜索执行记录"
          aria-label="搜索执行时间线"
          onChange={(event) => setQuery(event.target.value)}
        />
        <Segmented
          size="small"
          value={filter}
          onChange={(value) => setFilter(value as typeof filter)}
          options={[
            { value: 'all', label: '全部' },
            { value: 'output', label: '输出' },
            { value: 'tools', label: '工具' },
            { value: 'issues', label: '异常' },
          ]}
        />
        <label className={styles.followToggle}>
          <Switch size="small" checked={autoFollow} onChange={setAutoFollow} />
          <span>跟随</span>
        </label>
        <span className={styles.timelineCount}>{visibleTimeline.length}/{timeline.length}</span>
      </div>
      {visibleTimeline.length === 0 ? (
        <div className={styles.timelineEmpty}><Empty description="没有匹配的执行记录" /></div>
      ) : (
      <Virtuoso
        data={visibleTimeline}
        followOutput={autoFollow ? 'smooth' : false}
        initialTopMostItemIndex={Math.max(0, visibleTimeline.length - 1)}
        itemContent={(_, item) => (
          <article className={`${styles.timelineItem} ${styles[`timeline_${item.status || 'default'}`] || ''}`}>
            <div className={styles.timelineIcon}>{itemIcon(item)}</div>
            <div className={styles.timelineBody}>
              <div className={styles.timelineHeading}>
                <strong>{itemTitle(item)}</strong>
                <span>{item.status || item.type}</span>
              </div>
              {item.content ? (
                <TimelineContent content={item.content} />
              ) : null}
              {!item.content && item.payload ? (
                <pre className={styles.timelinePayload}>{JSON.stringify(item.payload, null, 2)}</pre>
              ) : null}
            </div>
          </article>
        )}
      />
      )}
    </div>
  );
}
