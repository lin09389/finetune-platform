import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApiGet = vi.hoisted(() => vi.fn());
const mockApiPost = vi.hoisted(() => vi.fn());
const mockApiDelete = vi.hoisted(() => vi.fn());

vi.mock('../services/api', () => ({
  apiClient: {
    get: mockApiGet,
    post: mockApiPost,
    delete: mockApiDelete,
  },
}));

vi.mock('antd', async () => {
  const actual = (await vi.importActual('antd')) as Record<string, any>;
  const Modal = Object.assign(actual.Modal, {
    confirm: vi.fn(({ onOk }: { onOk: () => void }) => onOk?.()),
  });
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
    Modal,
  };
});

import { ActionRecorder } from '../pages/ActionRecorder';

describe('ActionRecorder', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/record/actions') {
        return Promise.resolve({
          data: {
            actions: [
              { action_type: 'mouse_click', timestamp: 1234567890, data: { x: 100, y: 200 } },
              { action_type: 'key_press', timestamp: 1234567891, data: { key: 'a' } },
            ],
          },
        });
      }
      if (url === '/cua/record/files') {
        return Promise.resolve({
          data: { files: ['test1.json', 'test2.json'] },
        });
      }
      return Promise.resolve({ data: {} });
    });
    mockApiPost.mockResolvedValue({ data: {} });
    mockApiDelete.mockResolvedValue({ data: {} });
  });

  it('should render ActionRecorder page with title', async () => {
    render(<ActionRecorder />);
    expect(screen.getByText(/Action Recorder/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/record/actions');
    });
  });

  it('should display recording info alert', async () => {
    render(<ActionRecorder />);
    expect(screen.getByText(/Recording guide/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/record/files');
    });
  });

  it('should fetch actions on mount', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/record/actions');
    });
  });

  it('should fetch saved files on mount', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/record/files');
    });
  });

  it('should display start recording button initially', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Start Recording/i })).toBeInTheDocument();
    });
  });

  it('should display playback button', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Playback/i })).toBeInTheDocument();
    });
  });

  it('should display save button', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument();
    });
  });

  it('should display load button', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Load/i })).toBeInTheDocument();
    });
  });

  it('should display clear button', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Clear/i })).toBeInTheDocument();
    });
  });

  it('should handle start recording', async () => {
    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Start Recording/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Start Recording/i }));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/cua/record/action', { action: 'start' });
    });
  });

  it('should display operation count', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(screen.getByText('Action Count')).toBeInTheDocument();
    });
  });

  it('should display recording status as stopped initially', async () => {
    render(<ActionRecorder />);
    await waitFor(() => {
      expect(screen.getByText('Stopped')).toBeInTheDocument();
    });
  });

  it('should handle playback with no actions', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/record/actions') {
        return Promise.resolve({ data: { actions: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Playback/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Playback/i }));

    expect(mockApiPost).not.toHaveBeenCalledWith('/cua/record/play', expect.anything());
  });

  it('should handle clear actions', async () => {
    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Clear/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Clear/i }));

    await waitFor(() => {
      expect(mockApiDelete).toHaveBeenCalledWith('/cua/record/actions');
    });
  });

  it('should display action type tags', async () => {
    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByText('mouse_click')).toBeInTheDocument();
      expect(screen.getByText('key_press')).toBeInTheDocument();
    });
  });

  it('should display action table columns', async () => {
    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByText('Type')).toBeInTheDocument();
      expect(screen.getByText('Data')).toBeInTheDocument();
      expect(screen.getByText('Time')).toBeInTheDocument();
    });
  });

  it('should handle API errors gracefully', async () => {
    mockApiGet.mockRejectedValueOnce(new Error('Network error'));

    render(<ActionRecorder />);

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled();
    });
  });

  it('should display playback speed slider', async () => {
    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByText('Playback Speed')).toBeInTheDocument();
    });
  });

  it('should display playback mode select', async () => {
    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByText('Realtime')).toBeInTheDocument();
    });
  });

  it('should show pause and stop buttons when recording', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/record/actions') {
        return Promise.resolve({
          data: {
            is_recording: true,
            is_paused: false,
            actions: [
              { action_type: 'mouse_click', timestamp: 1234567890, data: { x: 100, y: 200 } },
            ],
          },
        });
      }
      if (url === '/cua/record/files') {
        return Promise.resolve({ data: { files: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pause/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Stop Recording/i })).toBeInTheDocument();
    });
  }, 15000);

  it('should handle pause recording', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/record/actions') {
        return Promise.resolve({
          data: {
            is_recording: true,
            is_paused: false,
            actions: [
              { action_type: 'mouse_click', timestamp: 1234567890, data: { x: 100, y: 200 } },
            ],
          },
        });
      }
      if (url === '/cua/record/files') {
        return Promise.resolve({ data: { files: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Pause/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Pause/i }));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/cua/record/action', { action: 'pause' });
    });
  }, 15000);

  it('should handle stop recording', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/record/actions') {
        return Promise.resolve({
          data: {
            is_recording: true,
            is_paused: false,
            actions: [
              { action_type: 'mouse_click', timestamp: 1234567890, data: { x: 100, y: 200 } },
            ],
          },
        });
      }
      if (url === '/cua/record/files') {
        return Promise.resolve({ data: { files: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Stop Recording/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Stop Recording/i }));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/cua/record/action', { action: 'stop' });
    });
  }, 15000);

  it('should display selected count', async () => {
    render(<ActionRecorder />);

    await waitFor(() => {
      expect(screen.getByText('Selected')).toBeInTheDocument();
    });
  });
});
