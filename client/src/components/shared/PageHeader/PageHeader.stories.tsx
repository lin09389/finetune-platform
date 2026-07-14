import { RocketOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import type { Meta, StoryObj } from '@storybook/react-vite';
import PageHeader from './index';

const meta = {
  title: 'Shared/PageHeader',
  component: PageHeader,
  parameters: { layout: 'padded' },
  tags: ['autodocs'],
} satisfies Meta<typeof PageHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basic: Story = { args: { title: '模型管理' } };

export const WithSubtitle: Story = {
  args: { title: '训练任务', subtitle: '管理 LoRA/QLoRA 微调任务，查看实时进度与检查点' },
};

export const WithIcon: Story = {
  args: {
    title: '推理服务',
    subtitle: '部署与调用微调后的模型',
    icon: <RocketOutlined />,
    iconBgColor: 'var(--accent-primary)',
  },
};

export const WithBreadcrumbs: Story = {
  args: {
    title: '评估详情',
    subtitle: '查看评估指标与人工评分',
    breadcrumbs: [
      { title: '首页', href: '/' },
      { title: '评估', href: '/evaluation' },
      { title: '详情' },
    ],
  },
};

export const WithActions: Story = {
  args: {
    title: '数据集',
    actions: (
      <>
        <Button>导入</Button>
        <Button type="primary">上传数据集</Button>
      </>
    ),
  },
};
