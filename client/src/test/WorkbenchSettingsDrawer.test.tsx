import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import WorkbenchSettingsDrawer from '../agent/components/WorkbenchSettingsDrawer';

vi.mock('../components/workspace/WorkspacePathPicker', () => ({
  default: ({ value, disabled }: { value: string; disabled?: boolean }) => (
    <div data-testid="workspace-path-picker" data-disabled={disabled ? 'true' : 'false'}>
      {value || '(empty)'}
    </div>
  ),
}));

describe('WorkbenchSettingsDrawer', () => {
  it('wires WorkspacePathPicker and disables path when session active', () => {
    const { rerender } = render(
      <WorkbenchSettingsDrawer
        open
        settings={{ projectPath: 'C:/repo', autonomyMode: 'safe_auto' }}
        sessionActive={false}
        onClose={vi.fn()}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId('workspace-path-picker')).toHaveAttribute('data-disabled', 'false');
    expect(screen.getByTestId('workspace-path-picker')).toHaveTextContent('C:/repo');

    rerender(
      <WorkbenchSettingsDrawer
        open
        settings={{ projectPath: 'C:/repo', autonomyMode: 'safe_auto' }}
        sessionActive
        onClose={vi.fn()}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('workspace-path-picker')).toHaveAttribute('data-disabled', 'true');
  });
});
