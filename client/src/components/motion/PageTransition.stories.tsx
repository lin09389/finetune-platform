import type { Meta, StoryObj } from '@storybook/react';
import { PageTransition } from './PageTransition';

const meta = {
  title: 'Motion/PageTransition',
  component: PageTransition,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
  argTypes: {
    locationKey: {
      control: 'text',
      description: 'Used by AnimatePresence to trigger enter/exit animations when changed.',
    },
  },
} satisfies Meta<typeof PageTransition>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    locationKey: 'page-1',
    className: 'min-h-[200px] p-8 flex items-center justify-center bg-bg-secondary m-4 rounded-xl',
    children: (
      <div className="text-center">
        <h2 className="text-2xl font-bold mb-4">Page Content</h2>
        <p className="opacity-80">Change the `locationKey` in controls to see the transition.</p>
      </div>
    ),
  },
};
