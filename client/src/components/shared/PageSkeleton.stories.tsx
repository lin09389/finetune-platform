import type { Meta, StoryObj } from '@storybook/react-vite';
import PageSkeleton from './PageSkeleton';

const meta = {
  title: 'Shared/PageSkeleton',
  component: PageSkeleton,
  parameters: { layout: 'fullscreen' },
  tags: ['autodocs'],
  argTypes: {
    cards: { control: 'number', min: 1, max: 12 },
    rows: { control: 'number', min: 1, max: 20 },
  },
} satisfies Meta<typeof PageSkeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { cards: 4, rows: 4 } };

export const Minimal: Story = { args: { cards: 2, rows: 2 } };

export const Dense: Story = { args: { cards: 6, rows: 8 } };
