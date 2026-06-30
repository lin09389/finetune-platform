import {
  ApartmentOutlined,
  CodeOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
import { Tooltip } from 'antd';
import styles from '../workbench/AgentWorkbench.module.css';

interface AgentPanelToolbarProps {
  workspaceOpen: boolean;
  taskCenterOpen: boolean;
  terminalOpen: boolean;
  onToggleWorkspace: () => void;
  onToggleTaskCenter: () => void;
  onToggleTerminal: () => void;
}

export default function AgentPanelToolbar({
  workspaceOpen,
  taskCenterOpen,
  terminalOpen,
  onToggleWorkspace,
  onToggleTaskCenter,
  onToggleTerminal,
}: AgentPanelToolbarProps) {
  const items = [
    {
      key: 'workspace',
      label: '工作区',
      shortcut: 'Ctrl+Shift+E',
      icon: <FolderOpenOutlined />,
      pressed: workspaceOpen,
      action: onToggleWorkspace,
    },
    {
      key: 'tasks',
      label: '任务中心',
      shortcut: 'Ctrl+Shift+J',
      icon: <ApartmentOutlined />,
      pressed: taskCenterOpen,
      action: onToggleTaskCenter,
    },
    {
      key: 'terminal',
      label: '终端',
      shortcut: 'Ctrl+`',
      icon: <CodeOutlined />,
      pressed: terminalOpen,
      action: onToggleTerminal,
    },
  ];

  return (
    <nav className={styles.panelToolbar} aria-label="工作台面板">
      {items.map((item) => (
        <Tooltip key={item.key} title={`${item.label} · ${item.shortcut}`}>
          <button
            type="button"
            className={item.pressed ? styles.panelToolbarButtonActive : styles.panelToolbarButton}
            aria-label={`${item.pressed ? '隐藏' : '显示'}${item.label}`}
            aria-pressed={item.pressed}
            onClick={item.action}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        </Tooltip>
      ))}
    </nav>
  );
}
