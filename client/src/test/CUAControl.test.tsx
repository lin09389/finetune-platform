import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApiGet = vi.hoisted(() => vi.fn());
const mockApiPost = vi.hoisted(() => vi.fn());

vi.mock('../services/api', () => ({
  apiClient: {
    get: mockApiGet,
    post: mockApiPost,
  },
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  };
});

import { CUAControl } from '../pages/CUAControl';

describe('CUAControl', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/screen/info') {
        return Promise.resolve({ data: { width: 1920, height: 1080, monitorCount: 2 } });
      }
      if (url === '/cua/mouse/position') {
        return Promise.resolve({ data: { x: 500, y: 300 } });
      }
      if (url === '/cua/safety/status') {
        return Promise.resolve({
          data: {
            enabled: true,
            permissionLevel: 'interactive',
            failsafeEnabled: true,
            auditEnabled: true,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    mockApiPost.mockResolvedValue({ data: {} });
  });

  it('loads base status on mount', async () => {
    render(<CUAControl />);
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/screen/info');
      expect(mockApiGet).toHaveBeenCalledWith('/cua/mouse/position');
      expect(mockApiGet).toHaveBeenCalledWith('/cua/safety/status');
    });
  });

  it('renders main panel title', async () => {
    render(<CUAControl />);
    expect(screen.getByText(/Computer Use Agent/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/screen/info');
    });
  });

  it('shows screenshot action in default tab', async () => {
    render(<CUAControl />);
    expect(screen.getByTestId('cua-btn-screenshot')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/mouse/position');
    });
  });

  it('renders mouse controls after switching tab', async () => {
    render(<CUAControl />);
    fireEvent.click(screen.getByRole('tab', { name: /鼠标控制/i }));
    await waitFor(() => {
      expect(screen.getByTestId('cua-input-x')).toBeInTheDocument();
      expect(screen.getByTestId('cua-input-y')).toBeInTheDocument();
      expect(screen.getByTestId('cua-btn-click')).toBeInTheDocument();
    });
  });

  it('handles fetch failures without crashing', async () => {
    mockApiGet.mockRejectedValueOnce(new Error('Network error'));
    render(<CUAControl />);
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled();
    });
    expect(screen.getByText(/当前环境无法读取屏幕能力/)).toBeInTheDocument();
  });
});
