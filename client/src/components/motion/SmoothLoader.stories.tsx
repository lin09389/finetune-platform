import type { Meta, StoryObj } from '@storybook/react';
import { SmoothLoader } from './SmoothLoader';

const meta = {
  title: 'Motion/SmoothLoader',
  component: SmoothLoader,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
    },
    color: {
      control: 'color',
    },
    fullscreen: {
      control: 'boolean',
    },
  },
} satisfies Meta<typeof SmoothLoader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    size: 'md',
    color: '#3b82f6',
  },
};

export const Small: Story = {
  args: {
    size: 'sm',
    color: '#10b981',
  },
};

export const Large: Story = {
  args: {
    size: 'lg',
    color: '#ef4444',
  },
};

export const Fullscreen: Story = {
  args: {
    size: 'lg',
    color: '#8b5cf6',
    fullscreen: true,
  },
  parameters: {
    docs: {
      description: {
        story: 'Shows a full screen backdrop blur overlay with the loader centered.',
      },
    },
  },
};
