import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import WorkspaceManager from '../pages/WorkspaceManager';

const { mockListWorkspaces, mockCreateWorkspace, mockUpdateWorkspace, mockDeleteWorkspace } =
  vi.hoisted(() => ({
    mockListWorkspaces: vi.fn(),
    mockCreateWorkspace: vi.fn(),
    mockUpdateWorkspace: vi.fn(),
    mockDeleteWorkspace: vi.fn(),
  }));
const mockMessage = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
};

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
  browseFolderBackend: vi.fn(),
  listWorkspaces: mockListWorkspaces,
  createWorkspace: mockCreateWorkspace,
  updateWorkspace: mockUpdateWorkspace,
  deleteWorkspace: mockDeleteWorkspace,
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  const Modal = Object.assign(actual.Modal, {
    confirm: vi.fn(({ onOk }: { onOk?: () => void }) => onOk?.()),
  });
  return {
    ...actual,
    App: {
      useApp: () => ({
        message: mockMessage,
      }),
    },
    Modal,
  };
});

describe('WorkspaceManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.values(mockMessage).forEach((mock) => mock.mockClear());
    mockListWorkspaces.mockResolvedValue([
      {
        id: 'ws-1',
        name: 'Test Workspace',
        description: 'A test workspace',
        created_at: '2024-01-15T10:00:00Z',
        updated_at: '2024-01-15T11:00:00Z',
        document_count: 5,
        vector_count: 100,
      },
    ]);
    mockCreateWorkspace.mockResolvedValue({});
    mockUpdateWorkspace.mockResolvedValue({});
    mockDeleteWorkspace.mockResolvedValue(undefined);
  });

  const renderComponent = () =>
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <WorkspaceManager />
      </MemoryRouter>,
    );

  it('fetches workspace list on mount', async () => {
    renderComponent();
    await waitFor(() => {
      expect(mockListWorkspaces).toHaveBeenCalled();
    });
  });

  it('renders workspace name', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument();
    });
  });

  it('shows create button', async () => {
    renderComponent();
    await waitFor(() => {
      expect(mockListWorkspaces).toHaveBeenCalled();
    });
    expect(screen.getByTestId('workspace-create-primary')).toBeInTheDocument();
  });

  it('opens modal when clicking create button', async () => {
    renderComponent();
    fireEvent.click(screen.getByTestId('workspace-create-primary'));
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('triggers delete flow', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument();
    });

    const deleteButton = screen.getByRole('button', { name: /删除/i });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(mockDeleteWorkspace).toHaveBeenCalledWith('ws-1');
    });
  });
});
