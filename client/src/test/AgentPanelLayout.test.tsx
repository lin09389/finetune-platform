import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AgentPanelToolbar from '../agent/components/AgentPanelToolbar';
import {
  DEFAULT_AGENT_PANEL_LAYOUT,
  MAX_DOCK_WIDTH,
  MAX_SESSION_WIDTH,
  MIN_TERMINAL_HEIGHT,
  MAX_WORKSPACE_SPLIT,
  persistAgentPanelLayout,
  readAgentPanelLayout,
} from '../agent/config/panelLayout';

describe('Agent panel layout', () => {
  it('restores valid preferences and clamps unsafe panel sizes', () => {
    const storage = {
      getItem: vi.fn().mockReturnValue(JSON.stringify({
        workspaceOpen: false,
        taskCenterOpen: true,
        terminalOpen: false,
        workspaceTab: 'diff',
        taskCenterTab: 'subagents',
        sessionWidth: 9999,
        dockWidth: 9999,
        terminalHeight: 12,
        workspaceSplit: 999,
      })),
    };

    expect(readAgentPanelLayout(storage)).toEqual({
      workspaceOpen: false,
      taskCenterOpen: true,
      terminalOpen: false,
      workspaceTab: 'diff',
      taskCenterTab: 'subagents',
      sessionWidth: MAX_SESSION_WIDTH,
      dockWidth: MAX_DOCK_WIDTH,
      terminalHeight: MIN_TERMINAL_HEIGHT,
      workspaceSplit: MAX_WORKSPACE_SPLIT,
    });
  });

  it('falls back safely when persisted state is corrupt', () => {
    expect(readAgentPanelLayout({ getItem: () => '{broken' })).toEqual(DEFAULT_AGENT_PANEL_LAYOUT);
  });

  it('persists the complete layout as one versioned preference', () => {
    const setItem = vi.fn();
    persistAgentPanelLayout(DEFAULT_AGENT_PANEL_LAYOUT, { setItem });
    expect(setItem).toHaveBeenCalledWith(
      'finetune.agent.panel-layout.v1',
      JSON.stringify(DEFAULT_AGENT_PANEL_LAYOUT),
    );
  });

  it('exposes independent, pressed panel switches', () => {
    const onToggleWorkspace = vi.fn();
    const onToggleTaskCenter = vi.fn();
    const onToggleTerminal = vi.fn();
    render(
      <AgentPanelToolbar
        workspaceOpen
        taskCenterOpen={false}
        terminalOpen
        onToggleWorkspace={onToggleWorkspace}
        onToggleTaskCenter={onToggleTaskCenter}
        onToggleTerminal={onToggleTerminal}
      />,
    );

    expect(screen.getByRole('button', { name: '隐藏工作区' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '显示任务中心' })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', { name: '隐藏终端' }));
    expect(onToggleTerminal).toHaveBeenCalledTimes(1);
  });
});
