import { Drawer, Form, Select, Typography } from 'antd';
import {
  FolderOpenOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import WorkspacePathPicker from '../../components/workspace/WorkspacePathPicker';
import type { AgentWorkbenchSettings } from '../config/workbenchSettings';
import styles from './WorkbenchSettingsDrawer.module.css';

interface WorkbenchSettingsDrawerProps {
  open: boolean;
  settings: AgentWorkbenchSettings;
  sessionActive: boolean;
  onClose: () => void;
  onChange: (next: AgentWorkbenchSettings) => void;
}

const AUTONOMY_OPTIONS = [
  {
    value: 'safe_auto' as const,
    label: '安全自动',
    description: '常规读写自动执行，敏感写入仍会请示',
  },
  {
    value: 'confirm_all' as const,
    label: '全部确认',
    description: '关键操作均需你确认后再执行',
  },
  {
    value: 'read_only' as const,
    label: '只读',
    description: '仅允许查看与检索，禁止改文件/执行命令',
  },
];

/**
 * 工作台设置抽屉：项目路径与自主模式。
 * 活跃会话锁定路径编辑（不热切换）；修改后用于下一次新建会话。
 */
export default function WorkbenchSettingsDrawer({
  open,
  settings,
  sessionActive,
  onClose,
  onChange,
}: WorkbenchSettingsDrawerProps) {
  return (
    <Drawer
      title={
        <span className={styles.drawerTitle}>
          <SettingOutlined />
          工作台设置
        </span>
      }
      open={open}
      onClose={onClose}
      width={440}
      destroyOnClose={false}
      className={styles.drawer}
    >
      <div className={styles.body}>
        <section className={styles.section}>
          <header className={styles.sectionHeader}>
            <FolderOpenOutlined />
            <div>
              <h3>工作区</h3>
              <p>Agent 读写文件与执行命令的根目录</p>
            </div>
          </header>
          <WorkspacePathPicker
            value={settings.projectPath}
            disabled={sessionActive}
            onChange={(projectPath) => onChange({
              ...settings,
              projectPath,
            })}
          />
        </section>

        <section className={styles.section}>
          <header className={styles.sectionHeader}>
            <SafetyCertificateOutlined />
            <div>
              <h3>自主模式</h3>
              <p>控制工具执行前的确认策略</p>
            </div>
          </header>
          <Form layout="vertical" className={styles.form}>
            <Form.Item className={styles.formItem}>
              <Select
                value={settings.autonomyMode}
                disabled={sessionActive}
                onChange={(autonomyMode) => onChange({ ...settings, autonomyMode })}
                options={AUTONOMY_OPTIONS.map((item) => ({
                  value: item.value,
                  label: item.label,
                }))}
                optionRender={(option) => {
                  const meta = AUTONOMY_OPTIONS.find((item) => item.value === option.value);
                  return (
                    <div className={styles.optionCard}>
                      <strong>{meta?.label || option.label}</strong>
                      <span>{meta?.description}</span>
                    </div>
                  );
                }}
              />
            </Form.Item>
            <Typography.Paragraph type="secondary" className={styles.autonomyHint}>
              {AUTONOMY_OPTIONS.find((item) => item.value === settings.autonomyMode)?.description}
            </Typography.Paragraph>
          </Form>
          {sessionActive ? (
            <Typography.Text type="secondary" className={styles.sessionHint}>
              当前已有会话：自主模式与工作区绑定在创建时确定，修改将用于下一次新任务。
            </Typography.Text>
          ) : null}
        </section>
      </div>
    </Drawer>
  );
}
