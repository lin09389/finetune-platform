import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import EmptyState from './index';

const meta = {
  title: 'Shared/EmptyState',
  component: EmptyState,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  args: { action: { text: '新建', onClick: fn() } },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { type: 'default' } };

export const DataEmpty: Story = { args: { type: 'data', description: '当前列表为空' } };

export const SearchEmpty: Story = { args: { type: 'search', description: '尝试使用不同的关键词搜索' } };

export const ErrorState: Story = { args: { type: 'error', description: '数据加载出错，请稍后重试' } };

export const NetworkError: Story = { args: { type: 'network', description: '请检查网络连接后重试' } };

export const Compact: Story = {
  args: { type: 'data', compact: true, description: '面板内紧凑空状态' },
  parameters: { layout: 'padded' },
};
