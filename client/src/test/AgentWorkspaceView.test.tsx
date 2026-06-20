import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentWorkspaceView from '../agent/components/AgentWorkspaceView';
import { createFlowScenario } from '../agent/testing/agentFlowScenarios';

const apiMocks = vi.hoisted(() => ({
  readWorkspaceFile: vi.fn(),
  writeWorkspaceFile: vi.fn(),
}));

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api');
  return {
    ...actual,
    readWorkspaceFile: apiMocks.readWorkspaceFile,
    writeWorkspaceFile: apiMocks.writeWorkspaceFile,
  };
});

describe('Agent Workspace business chains', () => {
  beforeEach(() => {
    apiMocks.readWorkspaceFile.mockReset();
    apiMocks.writeWorkspaceFile.mockReset();
    apiMocks.readWorkspaceFile.mockResolvedValue({ path: 'src/app.ts', content: 'const oldValue = 1;' });
    apiMocks.writeWorkspaceFile.mockResolvedValue({ status: 'ok', path: 'src/app.ts' });
  });

  it('loads, edits, and saves a changed file through workspace APIs', async () => {
    const { workspace } = createFlowScenario('files_diff_editor');
    render(
      <AgentWorkspaceView
        tab="files"
        workspace={workspace}
        onRecover={vi.fn()}
        onCancelSubagent={vi.fn()}
        onRunNextAction={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /src\/app.ts/ }));
    await waitFor(() => expect(apiMocks.readWorkspaceFile).toHaveBeenCalledWith({
      file_path: 'src/app.ts',
      project_path: 'C:/workspace/project',
    }));
    const editor = await screen.findByLabelText('文件内容');
    fireEvent.change(editor, { target: { value: 'const newValue = 2;' } });
    fireEvent.click(screen.getByRole('button', { name: '保存文件' }));
    await waitFor(() => expect(apiMocks.writeWorkspaceFile).toHaveBeenCalledWith({
      file_path: 'src/app.ts',
      content: 'const newValue = 2;',
      project_path: 'C:/workspace/project',
    }));
  });

  it('routes next-action buttons to the command owner', () => {
    const { workspace } = createFlowScenario('artifacts_next_actions');
    const onRunNextAction = vi.fn();
    render(
      <AgentWorkspaceView
        tab="artifacts"
        workspace={workspace}
        onRecover={vi.fn()}
        onCancelSubagent={vi.fn()}
        onRunNextAction={onRunNextAction}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Review' }));
    expect(onRunNextAction).toHaveBeenCalledWith(workspace.next_actions[0]);
  });
});
