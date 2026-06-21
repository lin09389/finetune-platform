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

  it('keeps multiple changed files in closable editor tabs', async () => {
    const { workspace } = createFlowScenario('files_diff_editor');
    workspace.changed_files.push({
      path: 'src/second.ts',
      status: 'modified',
      summary: 'Updated second file',
    });
    apiMocks.readWorkspaceFile.mockImplementation(({ file_path }: { file_path: string }) => Promise.resolve({
      path: file_path,
      content: `content:${file_path}`,
    }));
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
    await screen.findByDisplayValue('content:src/app.ts');
    fireEvent.click(screen.getByRole('button', { name: /src\/second.ts/ }));
    await screen.findByDisplayValue('content:src/second.ts');
    expect(screen.getByRole('tablist', { name: '已打开文件' })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '关闭 src/app.ts' }));
    expect(screen.getAllByRole('tab')).toHaveLength(1);
  });

  it('saves a dirty file with Ctrl+S and exposes plan completion progress', async () => {
    const { workspace } = createFlowScenario('files_diff_editor');
    const { rerender } = render(
      <AgentWorkspaceView
        tab="files"
        workspace={workspace}
        onRecover={vi.fn()}
        onCancelSubagent={vi.fn()}
        onRunNextAction={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /src\/app.ts/ }));
    const editor = await screen.findByLabelText('文件内容');
    fireEvent.change(editor, { target: { value: 'const shortcutSaved = true;' } });
    expect(screen.getByText(/未保存/)).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 's', ctrlKey: true });
    await waitFor(() => expect(apiMocks.writeWorkspaceFile).toHaveBeenCalledWith({
      file_path: 'src/app.ts',
      content: 'const shortcutSaved = true;',
      project_path: 'C:/workspace/project',
    }));

    const planScenario = createFlowScenario('execution_plan');
    planScenario.workspace.execution_plan = {
      ...planScenario.workspace.execution_plan!,
      nodes: [
        {
          id: 'node_1',
          title: 'Inspect',
          status: 'completed',
        },
        {
          id: 'node_2',
          title: 'Implement',
          status: 'running',
          agent_id: 'build',
          depends_on: ['node_1'],
          started_at: '2026-06-20T00:00:00Z',
          completed_at: '2026-06-20T00:01:05Z',
        },
      ],
    };
    rerender(
      <AgentWorkspaceView
        tab="plan"
        workspace={planScenario.workspace}
        onRecover={vi.fn()}
        onCancelSubagent={vi.fn()}
        onRunNextAction={vi.fn()}
      />,
    );
    expect(screen.getByText(/已完成/)).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    expect(screen.getByText('依赖: node_1')).toBeInTheDocument();
    expect(screen.getByText('耗时: 1m 5s')).toBeInTheDocument();
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
