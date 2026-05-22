import {
  ApartmentOutlined,
  ControlOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { Empty, Tabs } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import React, { useState } from 'react';
import styles from './AgentWorkbenchPanel.module.css';

interface AgentWorkbenchPanelProps {
  changedFiles: number;
  runContent: React.ReactNode;
  configContent: React.ReactNode;
  progressContent: React.ReactNode;
  fileTreeContent: React.ReactNode;
  editorContent: React.ReactNode;
}

const AgentWorkbenchPanel: React.FC<AgentWorkbenchPanelProps> = ({
  changedFiles,
  runContent,
  configContent,
  progressContent,
  fileTreeContent,
  editorContent,
}) => {
  const [fileTreeCollapsed, setFileTreeCollapsed] = useState(false);
  const tabItems = [
    {
      key: 'run',
      label: (
        <span className={styles.tabLabel}>
          <PlayCircleOutlined />
          运行
        </span>
      ),
      children: runContent,
    },
    {
      key: 'config',
      label: (
        <span className={styles.tabLabel}>
          <ControlOutlined />
          配置
        </span>
      ),
      children: configContent,
    },
    {
      key: 'progress',
      label: (
        <span className={styles.tabLabel}>
          <ApartmentOutlined />
          进度
        </span>
      ),
      children: progressContent,
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
      children: (
        <div className={styles.artifactsIde}>
          <AnimatePresence initial={false}>
            {!fileTreeCollapsed && (
              <motion.div
                key="file-tree"
                className={styles.artifactsFileTree}
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 200, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              >
                {fileTreeContent}
              </motion.div>
            )}
          </AnimatePresence>
          <button
            type="button"
            className={`${styles.treeToggleBtn} ${fileTreeCollapsed ? styles.treeToggleBtnCollapsed : ''}`}
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
      <Tabs className={styles.tabs} defaultActiveKey="run" items={tabItems} />
    </aside>
  );
};

export const WorkbenchEmpty: React.FC<{ description: string }> = ({ description }) => (
  <div className={styles.emptyWrap}>
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />
  </div>
);

export default AgentWorkbenchPanel;
