import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import WorkspaceManager from '../pages/WorkspaceManager';

const {
  mockListWorkspaces,
  mockCreateWorkspace,
  mockUpdateWorkspace,
  mockDeleteWorkspace,
  mockGetWorkspacePortabilityPreview,
  mockInspectWorkspacePackage,
  mockCommitWorkspaceImport,
  mockCreateWorkspaceContinuationSession,
} =
  vi.hoisted(() => ({
    mockListWorkspaces: vi.fn(),
    mockCreateWorkspace: vi.fn(),
    mockUpdateWorkspace: vi.fn(),
    mockDeleteWorkspace: vi.fn(),
    mockGetWorkspacePortabilityPreview: vi.fn(),
    mockInspectWorkspacePackage: vi.fn(),
    mockCommitWorkspaceImport: vi.fn(),
    mockCreateWorkspaceContinuationSession: vi.fn(),
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
  browseWorkspaceFolder: vi.fn(),
  listWorkspaces: mockListWorkspaces,
  createWorkspace: mockCreateWorkspace,
  updateWorkspace: mockUpdateWorkspace,
  deleteWorkspace: mockDeleteWorkspace,
  getWorkspacePortabilityPreview: mockGetWorkspacePortabilityPreview,
  exportWorkspacePackage: vi.fn(),
  inspectWorkspacePackage: mockInspectWorkspacePackage,
  commitWorkspaceImport: mockCommitWorkspaceImport,
  createWorkspaceContinuationSession: mockCreateWorkspaceContinuationSession,
  getWorkspacePortabilityError: (error: unknown) => ({ code: 'unknown', message: error instanceof Error ? error.message : '操作失败' }),
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
    mockGetWorkspacePortabilityPreview.mockResolvedValue({
      schema_version: 1,
      integrity: { algorithm: 'sha256', status: 'valid' },
      task_count: 1,
      resources: [],
      exclusions: ['源码内容', '模型权重'],
    });
    mockInspectWorkspacePackage.mockResolvedValue({
      import_token: 'import-token',
      preview: {
        schema_version: 1,
        integrity: { algorithm: 'sha256', status: 'valid' },
        task_count: 1,
        resources: [{ reference_id: 'dataset-1', kind: 'dataset', display_name: 'Training set', status: 'missing' }],
        exclusions: ['源码内容'],
      },
    });
    mockCommitWorkspaceImport.mockResolvedValue({
      workspace: { id: 'ws-imported', name: 'Imported demo' },
      continuations: [{ id: 'ctx-1', title: 'Finish training', mode: 'train', status: 'completed', blocked: false }],
    });
    mockCreateWorkspaceContinuationSession.mockResolvedValue({ id: 'session-new' });
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

  it('previews export exclusions before downloading a workspace package', async () => {
    renderComponent();
    await screen.findByText('Test Workspace');

    fireEvent.click(screen.getByRole('button', { name: /导出/i }));

    expect(await screen.findByText('不会包含的内容')).toBeInTheDocument();
    expect(screen.getByText('源码内容')).toBeInTheDocument();
  });

  it('inspects, rebinds missing resources, commits, and starts a new continuation session', async () => {
    renderComponent();
    fireEvent.click(screen.getByRole('button', { name: /导入 Workspace/i }));

    const file = new File(['manifest'], 'demo.ftworkspace', { type: 'application/zip' });
    fireEvent.change(screen.getByTestId('workspace-import-file'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /检查包内容/i }));

    expect(await screen.findByText('Training set')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/项目目录（必需/), { target: { value: 'C:/Projects/demo' } });
    fireEvent.change(screen.getByLabelText('Training set 的新位置'), { target: { value: 'C:/datasets/train.jsonl' } });
    mockCommitWorkspaceImport.mockRejectedValueOnce(new Error('请重试'));
    fireEvent.click(screen.getByRole('button', { name: /导入并创建工作空间/i }));

    expect(await screen.findByText('请重试')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /导入并创建工作空间/i }));

    await waitFor(() => {
      expect(mockCommitWorkspaceImport).toHaveBeenLastCalledWith(
        'import-token',
        expect.objectContaining({ resource_bindings: [{ reference_id: 'dataset-1', locator: 'C:/datasets/train.jsonl' }] }),
      );
    });
    fireEvent.click(await screen.findByRole('button', { name: /继续最近任务/i }));
    await waitFor(() => expect(mockCreateWorkspaceContinuationSession).toHaveBeenCalledWith('ws-imported', 'ctx-1'));
  }, 10_000);

  it('keeps unsupported local files out of the inspect flow', async () => {
    renderComponent();
    fireEvent.click(screen.getByRole('button', { name: /导入 Workspace/i }));

    fireEvent.change(screen.getByTestId('workspace-import-file'), {
      target: { files: [new File(['not a package'], 'notes.txt', { type: 'text/plain' })] },
    });

    expect(await screen.findByText('请选择 .ftworkspace 导入包。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /检查包内容/i })).toBeDisabled();
  });
});
