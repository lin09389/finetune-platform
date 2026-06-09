import {
  ApartmentOutlined,
  ControlOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Empty, Tabs } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import React, { useEffect, useRef, useState } from 'react';
import styles from './AgentWorkbenchPanel.module.css';

interface AgentWorkbenchPanelProps {
  activeKey?: string;
  changedFiles: number;
  runContent: React.ReactNode;
  configContent: React.ReactNode;
  progressContent: React.ReactNode;
  asyncTasksContent: React.ReactNode;
  planContent?: React.ReactNode;
  artifactLedgerContent?: React.ReactNode;
  approvalsContent?: React.ReactNode;
  executionContent?: React.ReactNode;
  runtimeContent?: React.ReactNode;
  inspectorContent?: React.ReactNode;
  fileTreeContent: React.ReactNode;
  editorContent: React.ReactNode;
  onActiveKeyChange?: (key: string) => void;
}

const AgentWorkbenchPanel: React.FC<AgentWorkbenchPanelProps> = ({
  activeKey,
  changedFiles,
  runContent,
  configContent,
  progressContent,
  asyncTasksContent,
  planContent,
  artifactLedgerContent,
  approvalsContent,
  executionContent,
  runtimeContent,
  inspectorContent,
  fileTreeContent,
  editorContent,
  onActiveKeyChange,
}) => {
  const [fileTreeCollapsed, setFileTreeCollapsed] = useState(false);
  const [treeWidth, setTreeWidth] = useState(240);
  const [internalActiveKey, setInternalActiveKey] = useState('execution');

  const startXRef = useRef<number>(0);
  const startWidthRef = useRef<number>(0);
  const resizeCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      resizeCleanupRef.current?.();
    };
  }, []);

  const handleResizeMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    resizeCleanupRef.current?.();
    startXRef.current = e.clientX;
    startWidthRef.current = treeWidth;

    const handleMouseMove = (me: MouseEvent) => {
      const deltaX = me.clientX - startXRef.current;
      const newWidth = Math.max(120, Math.min(startWidthRef.current + deltaX, 600));
      setTreeWidth(newWidth);
    };
    const handleMouseUp = () => {
      resizeCleanupRef.current?.();
    };
    const cleanup = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      resizeCleanupRef.current = null;
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    resizeCleanupRef.current = cleanup;
  };
  const resolvedActiveKey = activeKey ?? internalActiveKey;

  const handleTabChange = (key: string) => {
    if (activeKey === undefined) {
      setInternalActiveKey(key);
    }
    onActiveKeyChange?.(key);
  };

  const tabItems = [
    {
      key: 'plan',
      label: (
        <span className={styles.tabLabel}>
          <UnorderedListOutlined />
          计划
        </span>
      ),
      children: planContent || runContent,
    },
    {
      key: 'approvals',
      label: (
        <span className={styles.tabLabel}>
          <ControlOutlined />
          确认
        </span>
      ),
      children: approvalsContent || inspectorContent || runContent,
    },
    {
      key: 'execution',
      label: (
        <span className={styles.tabLabel}>
          <PlayCircleOutlined />
          执行
        </span>
      ),
      children: executionContent || progressContent || runContent,
    },
    {
      key: 'artifacts',
      label: (
        <span className={styles.tabLabel}>
          <FileTextOutlined />
          产物
          {changedFiles > 0 ? <em>{changedFiles}</em> : null}
        </span>
      ),
      children: artifactLedgerContent || runContent,
    },
    {
      key: 'subagents',
      label: (
        <span className={styles.tabLabel}>
          <ThunderboltOutlined />
          子任务
        </span>
      ),
      children: asyncTasksContent,
    },
    {
      key: 'runtime',
      label: (
        <span className={styles.tabLabel}>
          <ApartmentOutlined />
          运行时
        </span>
      ),
      children: runtimeContent || configContent || runContent,
    },
    {
      key: 'files',
      label: (
        <span className={styles.tabLabel}>
          <FileTextOutlined />
          文件
          {changedFiles > 0 ? <em>{changedFiles}</em> : null}
        </span>
      ),
      children: (
        <div className={styles.artifactsIde}>
          <AnimatePresence initial={false}>
            {!fileTreeCollapsed && (
              <motion.div
                key="file-tree"
                className={styles.artifactsFileTree}
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: treeWidth, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
              >
                {fileTreeContent}
              </motion.div>
            )}
          </AnimatePresence>
          {!fileTreeCollapsed && (
            <div
              className={styles.resizer}
              onMouseDown={handleResizeMouseDown}
              title="拖拽调整宽度"
            />
          )}
          <button
            type="button"
            className={`${styles.treeToggleBtn} ${fileTreeCollapsed ? styles.treeToggleBtnCollapsed : ''}`}
            style={{ left: fileTreeCollapsed ? '-8px' : `calc(${treeWidth}px - 8px)` }}
            onClick={() => setFileTreeCollapsed((v) => !v)}
            title={fileTreeCollapsed ? '展开文件树' : '折叠文件树'}
            aria-label={fileTreeCollapsed ? '展开文件树' : '折叠文件树'}
          >
            {fileTreeCollapsed ? '›' : '‹'}
          </button>
          <div className={styles.artifactsEditor}>
            {editorContent}
          </div>
        </div>
      ),
    },
  ];

  return (
    <aside className={styles.panel} aria-label="Agent 工具区">
      <Tabs className={styles.tabs} activeKey={resolvedActiveKey} onChange={handleTabChange} items={tabItems} />
    </aside>
  );
};

export const WorkbenchEmpty: React.FC<{ description: string }> = ({ description }) => (
  <div className={styles.emptyWrap}>
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />
  </div>
);

export default AgentWorkbenchPanel;
