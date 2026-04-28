import type { Meta, StoryObj } from '@storybook/react';
import { InteractiveButton } from './InteractiveButton';

const meta = {
  title: 'Motion/InteractiveButton',
  component: InteractiveButton,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'glass', 'ghost'],
    },
    disabled: {
      control: 'boolean',
    },
    ripple: {
      control: 'boolean',
    },
  },
} satisfies Meta<typeof InteractiveButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {
    variant: 'primary',
    children: 'Interactive Button',
    ripple: true,
  },
};

export const Secondary: Story = {
  args: {
    variant: 'secondary',
    children: 'Secondary Action',
    ripple: true,
  },
};

export const Glass: Story = {
  args: {
    variant: 'glass',
    children: 'Glass Effect',
    ripple: true,
  },
  parameters: {
    backgrounds: {
      default: 'dark',
    },
  },
};

export const Disabled: Story = {
  args: {
    variant: 'primary',
    children: 'Disabled Button',
    disabled: true,
  },
};
