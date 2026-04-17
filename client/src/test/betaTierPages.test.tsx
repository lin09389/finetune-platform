import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
    Modal,
  };
});

import ModelHub from '../pages/ModelHub';
import ProjectContext from '../pages/ProjectContext';
import WorkspaceManager from '../pages/WorkspaceManager';

describe('beta tier page copy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/model-center/source')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ current_source: 'modelscope', default_source: 'modelscope' }),
        });
      }
      if (url.includes('/model-center/suggestions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ suggestions: [], default_source: 'modelscope' }),
        });
      }
      if (url.includes('/model-center/local')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.includes('/workspace/workspaces')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.includes('/context/projects')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, projects: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  it('shows beta capability framing on ModelHub', async () => {
    render(<ModelHub />);

    await waitFor(() => {
      expect(screen.getByText(/Beta 能力：搜索、下载并管理本地模型/i)).toBeInTheDocument();
      expect(screen.getByText(/搜索结果、下载速度和可访问性会随/i)).toBeInTheDocument();
    });
  });

  it('shows beta capability framing on WorkspaceManager', async () => {
    render(<WorkspaceManager />);

    await waitFor(() => {
      expect(screen.getByText(/Beta 能力：管理知识库工作空间/i)).toBeInTheDocument();
      expect(screen.getByText(/工作空间结构已经可试用/i)).toBeInTheDocument();
    });
  });

  it('shows beta capability framing on ProjectContext', async () => {
    render(<ProjectContext />);

    await waitFor(() => {
      expect(screen.getByText(/Beta 能力：扫描并索引本地项目/i)).toBeInTheDocument();
      expect(screen.getByText(/页面可用不代表索引一定完整/i)).toBeInTheDocument();
    });
  });
});
