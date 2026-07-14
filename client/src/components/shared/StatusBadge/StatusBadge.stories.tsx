import type { Meta, StoryObj } from '@storybook/react-vite';
import StatusBadge, { type StatusType } from './index';

const meta = {
  title: 'Shared/StatusBadge',
  component: StatusBadge,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'select',
      options: [
        'success',
        'error',
        'warning',
        'info',
        'processing',
        'pending',
        'stopped',
        'paused',
        'completed',
        'failed',
        'running',
        'cancelled',
      ] as StatusType[],
    },
    size: { control: 'select', options: ['small', 'default'] },
  },
} satisfies Meta<typeof StatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Success: Story = { args: { status: 'success' } };
export const Error: Story = { args: { status: 'error' } };
export const Warning: Story = { args: { status: 'warning' } };
export const Processing: Story = { args: { status: 'processing' } };
export const Pending: Story = { args: { status: 'pending' } };
export const Running: Story = { args: { status: 'running' } };
export const Completed: Story = { args: { status: 'completed' } };
export const Failed: Story = { args: { status: 'failed' } };
export const Stopped: Story = { args: { status: 'stopped' } };
export const Cancelled: Story = { args: { status: 'cancelled' } };

export const SmallSize: Story = { args: { status: 'success', size: 'small' } };

export const CustomText: Story = { args: { status: 'running', text: '训练中' } };

export const NoIcon: Story = { args: { status: 'success', showIcon: false } };
