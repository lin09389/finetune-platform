import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WorkspacePathPicker from '../components/workspace/WorkspacePathPicker';

const {
  getAllowedWorkspaceRoots,
  listWorkspaces,
  validateWorkspacePath,
  browseWorkspaceFolder,
  createWorkspace,
} = vi.hoisted(() => ({
  getAllowedWorkspaceRoots: vi.fn(),
  listWorkspaces: vi.fn(),
  validateWorkspacePath: vi.fn(),
  browseWorkspaceFolder: vi.fn(),
  createWorkspace: vi.fn(),
}));

vi.mock('../services/api', () => ({
  getAllowedWorkspaceRoots,
  listWorkspaces,
  validateWorkspacePath,
  browseWorkspaceFolder,
  createWorkspace,
}));

describe('WorkspacePathPicker', () => {
  beforeEach(() => {
    localStorage.clear();
    getAllowedWorkspaceRoots.mockResolvedValue({
      default_project_path: 'C:/repo',
      roots: [{ path: 'C:/repo', source: 'default', label: 'repo' }],
    });
    listWorkspaces.mockResolvedValue([
      { id: 'ws1', name: 'Demo', local_path: 'C:/repo/demo', status: 'active' },
    ]);
    validateWorkspacePath.mockImplementation(async (path: string | null) => {
      if (!path) {
        return {
          ok: true,
          resolved_path: 'C:/repo',
          allowed: true,
          exists: true,
          is_dir: true,
          needs_register: false,
          message: null,
          error_code: null,
        };
      }
      if (path === 'C:/outside') {
        return {
          ok: false,
          resolved_path: 'C:/outside',
          allowed: false,
          exists: true,
          is_dir: true,
          needs_register: true,
          message: '路径不在允许的工作区根内',
          error_code: 'path_not_allowed',
        };
      }
      if (path === 'C:/missing') {
        return {
          ok: false,
          resolved_path: 'C:/missing',
          allowed: false,
          exists: false,
          is_dir: false,
          needs_register: false,
          message: '路径不存在。',
          error_code: 'path_missing',
        };
      }
      return {
        ok: true,
        resolved_path: path,
        allowed: true,
        exists: true,
        is_dir: true,
        needs_register: false,
        message: null,
        error_code: null,
      };
    });
    browseWorkspaceFolder.mockResolvedValue('C:/repo/demo');
    createWorkspace.mockResolvedValue({
      id: 'ws_new',
      name: 'outside',
      local_path: 'C:/outside',
      status: 'active',
    });
  });

  it('validates typed path and shows success', async () => {
    const onChange = vi.fn();
    render(<WorkspacePathPicker value="C:/repo/demo" onChange={onChange} />);

    await waitFor(() => {
      expect(validateWorkspacePath).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-path-status')).toHaveTextContent('可用');
    });
  });

  it('browse button applies selected path', async () => {
    const onChange = vi.fn();
    render(<WorkspacePathPicker value="" onChange={onChange} />);

    fireEvent.click(screen.getByTestId('workspace-path-browse'));
    await waitFor(() => {
      expect(browseWorkspaceFolder).toHaveBeenCalled();
      expect(onChange).toHaveBeenCalledWith('C:/repo/demo');
    });
  });

  it('shows register action for out-of-root path and registers', async () => {
    const onChange = vi.fn();
    const onValidated = vi.fn();
    const { rerender } = render(
      <WorkspacePathPicker value="C:/outside" onChange={onChange} onValidated={onValidated} />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-path-register')).toBeInTheDocument();
    });

    validateWorkspacePath.mockResolvedValueOnce({
      ok: false,
      resolved_path: 'C:/outside',
      allowed: false,
      exists: true,
      is_dir: true,
      needs_register: true,
      message: '路径不在允许的工作区根内',
      error_code: 'path_not_allowed',
    });

    fireEvent.click(screen.getByTestId('workspace-path-register'));
    await waitFor(() => {
      expect(createWorkspace).toHaveBeenCalledWith(
        expect.objectContaining({ local_path: 'C:/outside' }),
      );
    });

    // After register, validate is called again
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('C:/outside');
    });

    rerender(<WorkspacePathPicker value="C:/outside" onChange={onChange} onValidated={onValidated} />);
  });

  it('shows failure for missing path', async () => {
    render(<WorkspacePathPicker value="C:/missing" onChange={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('workspace-path-status')).toHaveTextContent('路径不存在');
    });
  });

  it('disables controls when session is locked and shows hint', async () => {
    render(<WorkspacePathPicker value="C:/repo" onChange={vi.fn()} disabled />);
    expect(screen.getByTestId('workspace-path-input')).toBeDisabled();
    expect(screen.getByTestId('workspace-path-browse')).toBeDisabled();
    expect(screen.getByTestId('workspace-path-locked-hint')).toBeInTheDocument();
  });
});
