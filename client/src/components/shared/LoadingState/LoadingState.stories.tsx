import type { Meta, StoryObj } from '@storybook/react-vite';
import LoadingState from './index';

const meta = {
  title: 'Shared/LoadingState',
  component: LoadingState,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  argTypes: {
    type: { control: 'select', options: ['spinner', 'skeleton', 'dots', 'card', 'page'] },
    size: { control: 'select', options: ['small', 'default', 'large'] },
  },
} satisfies Meta<typeof LoadingState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Spinner: Story = { args: { type: 'spinner', tip: '正在加载...' } };

export const Dots: Story = { args: { type: 'dots', tip: '处理中' } };

export const Skeleton: Story = { args: { type: 'skeleton' } };

export const Card: Story = { args: { type: 'card' } };

export const Page: Story = {
  args: { type: 'page', tip: '正在加载工作台...' },
  parameters: { layout: 'fullscreen' },
};

export const LoadedWithChildren: Story = {
  args: { type: 'spinner', loading: false, children: <div style={{ padding: 24 }}>内容已就绪</div> },
};
