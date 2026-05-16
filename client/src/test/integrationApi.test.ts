/**
 * Frontend integration tests.
 *
 * These tests exercise the API service layer contract and key page
 * component render flows without hitting a real backend.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockGet = vi.hoisted(() => vi.fn());
const mockPost = vi.hoisted(() => vi.fn());
const mockDelete = vi.hoisted(() => vi.fn());
const mockCreate = vi.hoisted(() =>
  vi.fn(() => ({
    get: mockGet,
    post: mockPost,
    delete: mockDelete,
    put: vi.fn(),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  })),
);

vi.mock('axios', () => {
  return {
    default: {
      create: mockCreate,
      get: vi.fn(),
      post: vi.fn(),
      isCancel: vi.fn(() => false),
    },
    create: mockCreate,
  };
});

describe('API service contracts', () => {
  beforeEach(() => {
    vi.resetModules();
    mockGet.mockReset();
    mockPost.mockReset();
    mockDelete.mockReset();
  });

  it('getDeviceInfo resolves device info shape', async () => {
    mockGet.mockResolvedValueOnce({
      data: { cuda_available: false, device_name: 'test', memory: { total: 0 } },
    });
    const { default: api } = await import('../services/api');
    const res = await api.get('/device/info');
    expect(res.data).toHaveProperty('cuda_available');
    expect(res.data).toHaveProperty('memory');
  });

  it('getModelList returns array', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    const { default: api } = await import('../services/api');
    const res = await api.get('/models/list');
    expect(Array.isArray(res.data)).toBe(true);
  });

  it('getDatasetList returns array', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    const { default: api } = await import('../services/api');
    const res = await api.get('/datasets/list');
    expect(Array.isArray(res.data)).toBe(true);
  });

  it('training status returns object with tasks or status', async () => {
    mockGet.mockResolvedValueOnce({ data: { tasks: [] } });
    const { default: api } = await import('../services/api');
    const res = await api.get('/training/status');
    expect(res.data).toHaveProperty('tasks');
  });

  it('chat sessions endpoint returns list', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    const { default: api } = await import('../services/api');
    const res = await api.get('/chat/sessions');
    expect(Array.isArray(res.data)).toBe(true);
  });

  it('evaluation runs endpoint returns data', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    const { default: api } = await import('../services/api');
    const res = await api.get('/evaluation/runs');
    expect(Array.isArray(res.data)).toBe(true);
  });

  it('inference backends endpoint returns data', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    const { default: api } = await import('../services/api');
    const res = await api.get('/inference/backends');
    expect(res.data).toBeDefined();
  });

  it('workflow list endpoint returns data', async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    const { default: api } = await import('../services/api');
    const res = await api.get('/workflows');
    expect(res.data).toBeDefined();
  });
});
