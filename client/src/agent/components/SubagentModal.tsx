import { Form, Input, Modal, Select } from 'antd';

interface SubagentModalProps {
  open: boolean;
  confirmLoading: boolean;
  subagentTargets: string[];
  onClose: () => void;
  onStart: (agentName: string, description: string) => Promise<void>;
}

/**
 * 启动子 Agent 的模态框。表单校验与启动成功后关闭/重置由本组件负责；
 * 启动失败时保持打开以供重试（runtime state 已暴露可操作错误）。
 */
export default function SubagentModal({
  open,
  confirmLoading,
  subagentTargets,
  onClose,
  onStart,
}: SubagentModalProps) {
  const [form] = Form.useForm<{ agentName: string; description: string }>();
  return (
    <Modal
      title="启动子 Agent"
      open={open}
      okText="启动"
      cancelText="取消"
      confirmLoading={confirmLoading}
      onCancel={onClose}
      onOk={() => {
        void form.validateFields().then(async (values) => {
          await onStart(values.agentName, values.description);
          form.resetFields();
          onClose();
        });
      }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ agentName: subagentTargets[0] || 'explore' }}
      >
        <Form.Item name="agentName" label="Agent" rules={[{ required: true }]}>
          <Select options={subagentTargets.map((target) => ({ value: target, label: target }))} />
        </Form.Item>
        <Form.Item name="description" label="任务说明" rules={[{ required: true, min: 3 }]}>
          <Input.TextArea rows={4} placeholder="说明希望子 Agent 独立完成的工作" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
