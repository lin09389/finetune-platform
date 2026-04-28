import type { Meta, StoryObj } from '@storybook/react';
import { GlassHoverCard } from './GlassHoverCard';

const meta = {
  title: 'Motion/GlassHoverCard',
  component: GlassHoverCard,
  parameters: {
    layout: 'centered',
    backgrounds: {
      default: 'dark',
      values: [
        { name: 'light', value: '#f8fafc' },
        { name: 'dark', value: '#0f172a' },
      ],
    },
  },
  tags: ['autodocs'],
  argTypes: {
    tilt3D: {
      control: 'boolean',
    },
  },
} satisfies Meta<typeof GlassHoverCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    tilt3D: false,
    className: 'w-64 h-48 p-6 flex flex-col items-center justify-center text-center',
    children: (
      <>
        <h3 className="text-xl font-bold mb-2">Hover Me</h3>
        <p className="text-sm opacity-80">Smooth lift effect with glassmorphism texture.</p>
      </>
    ),
  },
};

export const With3DTilt: Story = {
  args: {
    tilt3D: true,
    className: 'w-64 h-48 p-6 flex flex-col items-center justify-center text-center',
    children: (
      <>
        <h3 className="text-xl font-bold mb-2">3D Hover</h3>
        <p className="text-sm opacity-80">Scale and tilt on hover.</p>
      </>
    ),
  },
};
