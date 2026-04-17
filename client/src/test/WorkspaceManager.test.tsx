import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WorkspaceManager from '../pages/WorkspaceManager';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

vi.mock('antd', async () => {
  const actual = (await vi.importActual('antd')) as Record<string, any>;
  const Modal = Object.assign(actual.Modal, {
    confirm: vi.fn(({ onOk }: { onOk?: () => void }) => onOk?.()),
  });
  return {
    ...actual,
    App: {
      useApp: () => ({
        message: {
          success: vi.fn(),
          error: vi.fn(),
          warning: vi.fn(),
        },
      }),
    },
    Modal,
  };
});

describe('WorkspaceManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (
        url.includes('/workspace/workspaces') &&
        (!init || !init.method || init.method === 'GET')
      ) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                id: 'ws-1',
                name: 'Test Workspace',
                description: 'A test workspace',
                created_at: '2024-01-15T10:00:00Z',
                updated_at: '2024-01-15T11:00:00Z',
                document_count: 5,
                vector_count: 100,
              },
            ]),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  it('fetches workspace list on mount', async () => {
    render(<WorkspaceManager />);
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/workspace/workspaces');
    });
  });

  it('renders workspace name', async () => {
    render(<WorkspaceManager />);
    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument();
    });
  });

  it('shows create button', async () => {
    render(<WorkspaceManager />);
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/workspace/workspaces');
    });
    expect(screen.getByTestId('workspace-create-primary')).toBeInTheDocument();
  });

  it('opens modal when clicking create button', async () => {
    render(<WorkspaceManager />);
    fireEvent.click(screen.getByTestId('workspace-create-primary'));
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('triggers delete flow', async () => {
    render(<WorkspaceManager />);
    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument();
    });

    const deleteButton = screen.getByRole('button', { name: /删除/i });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/workspace/workspaces/ws-1', {
        method: 'DELETE',
      });
    });
  });
});
