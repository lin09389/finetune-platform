import { Drawer, Form, Input, Select } from 'antd';
import type { AgentWorkbenchSettings } from '../config/workbenchSettings';

interface WorkbenchSettingsDrawerProps {
  open: boolean;
  settings: AgentWorkbenchSettings;
  sessionActive: boolean;
  onClose: () => void;
  onChange: (next: AgentWorkbenchSettings) => void;
}

/**
 * 工作台设置抽屉：项目路径与自主模式。会话创建后两者均不可修改。
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
      title="工作台设置"
      open={open}
      onClose={onClose}
      width={360}
    >
      <Form layout="vertical">
        <Form.Item label="项目路径" extra="留空时使用后端默认工作区。新会话创建后不可修改。">
          <Input
            value={settings.projectPath}
            disabled={sessionActive}
            placeholder="例如 /path/to/project 或 C:\\projects\\my-app"
            onChange={(event) => onChange({
              ...settings,
              projectPath: event.target.value,
            })}
          />
        </Form.Item>
        <Form.Item label="自主模式">
          <Select
            value={settings.autonomyMode}
            disabled={sessionActive}
            onChange={(autonomyMode) => onChange({ ...settings, autonomyMode })}
            options={[
              { value: 'safe_auto', label: '安全自动' },
              { value: 'confirm_all', label: '全部确认' },
              { value: 'read_only', label: '只读' },
            ]}
          />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
