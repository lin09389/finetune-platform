import {
  ApartmentOutlined,
  ControlOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { Empty, Tabs } from 'antd';
import React from 'react';
import styles from './AgentWorkbenchPanel.module.css';

interface AgentWorkbenchPanelProps {
  changedFiles: number;
  runContent: React.ReactNode;
  configContent: React.ReactNode;
  progressContent: React.ReactNode;
  artifactsContent: React.ReactNode;
}

const AgentWorkbenchPanel: React.FC<AgentWorkbenchPanelProps> = ({
  changedFiles,
  runContent,
  configContent,
  progressContent,
  artifactsContent,
}) => {
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
      children: artifactsContent,
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
