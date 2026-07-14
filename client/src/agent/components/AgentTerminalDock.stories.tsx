import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';
import AgentTerminalDock from './AgentTerminalDock';
import type { PanelResizeHandlers } from '../workbench/usePanelResize';

const noopResize = {
  beginResize: fn(),
  resizePanel: fn(),
  endResize: fn(),
  resizePanelWithKeyboard: fn(),
  resetPanelSize: fn(),
} as unknown as PanelResizeHandlers;

const meta = {
  title: 'Agent/AgentTerminalDock',
  component: AgentTerminalDock,
  parameters: {
    layout: 'fullscreen',
    backgrounds: {
      default: 'dark',
      values: [
        { name: 'light', value: '#faf9f5' },
        { name: 'dark', value: '#1a1a18' },
      ],
    },
  },
  tags: ['autodocs'],
  args: {
    visible: true,
    isDesktop: true,
    terminalHeight: 280,
    resize: noopResize,
    onClose: fn(),
  },
} satisfies Meta<typeof AgentTerminalDock>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 终端面板已挂载（xterm 懒加载中或已就绪）。 */
export const Mounted: Story = {
  args: { mounted: true, timeline: [] },
};

/** 终端面板未运行，显示空状态提示。 */
export const NotMounted: Story = {
  args: { mounted: false, timeline: [] },
};

/** 面板隐藏时（DOM 仍在以保持 xterm 实例）。 */
export const Hidden: Story = {
  args: { mounted: true, visible: false, timeline: [] },
};
