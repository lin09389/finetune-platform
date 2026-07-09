import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApiGet = vi.hoisted(() => vi.fn());

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://127.0.0.1:8010',
  apiClient: {
    get: mockApiGet,
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import ExperimentalRouteGuard from '../capability/ExperimentalRouteGuard';
import { useAppStore } from '../store/appStore';

describe('ExperimentalRouteGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAppStore.setState({ backendStatus: 'connected' });
  });

  it('does not block /cloud-api when experimental_enabled is false', async () => {
    mockApiGet.mockResolvedValue({
      data: { experimental_enabled: false },
    });

    render(
      <MemoryRouter>
        <ExperimentalRouteGuard path="/cloud-api">
          <div data-testid="cloud-api-content">Cloud API body</div>
        </ExperimentalRouteGuard>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('cloud-api-content')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('experimental-disabled-guard')).not.toBeInTheDocument();
    // Guard must not require /api/info for non-experimental routes
    expect(mockApiGet).not.toHaveBeenCalled();
  });

  it('blocks experimental /gateway when experimental_enabled is false', async () => {
    mockApiGet.mockResolvedValue({
      data: { experimental_enabled: false },
    });

    render(
      <MemoryRouter>
        <ExperimentalRouteGuard path="/gateway">
          <div data-testid="gateway-content">Gateway body</div>
        </ExperimentalRouteGuard>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('experimental-disabled-guard')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('gateway-content')).not.toBeInTheDocument();
    expect(mockApiGet).toHaveBeenCalledWith('/api/info');
  });

  it('allows experimental /gateway when experimental_enabled is true', async () => {
    mockApiGet.mockResolvedValue({
      data: { experimental_enabled: true },
    });

    render(
      <MemoryRouter>
        <ExperimentalRouteGuard path="/gateway">
          <div data-testid="gateway-content">Gateway body</div>
        </ExperimentalRouteGuard>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('gateway-content')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('experimental-disabled-guard')).not.toBeInTheDocument();
  });
});
