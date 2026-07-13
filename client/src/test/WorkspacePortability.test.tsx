import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockApiClient } = vi.hoisted(() => ({
  mockApiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockApiClient),
    isCancel: vi.fn(() => false),
  },
}));

import {
  commitWorkspaceImport,
  createWorkspaceContinuationSession,
  exportWorkspacePackage,
  getWorkspacePortabilityError,
  inspectWorkspacePackage,
} from '../services/api';

describe('workspace portability API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiClient.post.mockResolvedValue({ data: {} });
    mockApiClient.get.mockResolvedValue({ data: new Blob(['archive']) });
  });

  it('uploads an ftworkspace package as multipart form data for inspect', async () => {
    const file = new File(['manifest'], 'demo.ftworkspace', { type: 'application/zip' });

    await inspectWorkspacePackage(file);

    expect(mockApiClient.post).toHaveBeenCalledWith(
      '/workspace/imports/inspect',
      expect.any(FormData),
      expect.objectContaining({ headers: expect.objectContaining({ 'Content-Type': 'multipart/form-data' }) }),
    );
    const formData = mockApiClient.post.mock.calls[0]?.[1] as FormData;
    expect((formData.get('file') as File).name).toBe('demo.ftworkspace');
  });

  it('downloads workspace exports as binary data', async () => {
    await exportWorkspacePackage('ws-1');

    expect(mockApiClient.post).toHaveBeenCalledWith(
      '/workspace/workspaces/ws-1/exports',
      undefined,
      expect.objectContaining({ responseType: 'blob' }),
    );
  });

  it('commits bindings and creates a new continuation session through the portability endpoints', async () => {
    await commitWorkspaceImport('import-token', {
      name: 'Imported demo',
      project_path: 'C:/Projects/demo',
      resource_bindings: [{ reference_id: 'project', locator: 'C:/Projects/demo' }],
    });
    await createWorkspaceContinuationSession('ws-local', 'ctx-1');

    expect(mockApiClient.post).toHaveBeenNthCalledWith(
      1,
      '/workspace/imports/import-token/commit',
      expect.objectContaining({ name: 'Imported demo' }),
    );
    expect(mockApiClient.post).toHaveBeenNthCalledWith(
      2,
      '/workspace/workspaces/ws-local/continuations/ctx-1/sessions',
      undefined,
    );
  });

  it('decodes stable portability error codes without exposing transport details', () => {
    expect(
      getWorkspacePortabilityError({
        response: { data: { detail: { code: 'unsupported_version', message: 'version 2 is not supported' } } },
      }),
    ).toEqual({ code: 'unsupported_version', message: 'version 2 is not supported' });
  });
});
