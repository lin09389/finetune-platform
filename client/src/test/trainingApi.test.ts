import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApiClientGet = vi.hoisted(() => vi.fn());
const mockApiClientPost = vi.hoisted(() => vi.fn());
const mockGetTrainingFailureAnalytics = vi.hoisted(() => vi.fn());
const mockGetTrainingCheckpoints = vi.hoisted(() => vi.fn());
const mockGetTrainingHistory = vi.hoisted(() => vi.fn());
const mockGetTrainingRecoveryOptions = vi.hoisted(() => vi.fn());
const mockResumeTraining = vi.hoisted(() => vi.fn());
const mockStartSwiftTraining = vi.hoisted(() => vi.fn());
const mockStartTraining = vi.hoisted(() => vi.fn());
const mockStopTraining = vi.hoisted(() => vi.fn());
const mockSubscribeTrainingProgress = vi.hoisted(() => vi.fn());

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
  apiClient: {
    get: mockApiClientGet,
    post: mockApiClientPost,
  },
  checkTrainingPreflight: vi.fn((config) =>
    mockApiClientPost('/training/preflight', config).then((r: any) => r.data),
  ),
  getTrainingFailureAnalytics: mockGetTrainingFailureAnalytics,
  getTrainingCheckpoints: mockGetTrainingCheckpoints,
  getTrainingHistory: mockGetTrainingHistory,
  getTrainingRecoveryOptions: mockGetTrainingRecoveryOptions,
  resumeTraining: mockResumeTraining,
  startSwiftTraining: mockStartSwiftTraining,
  startTraining: mockStartTraining,
  stopTraining: mockStopTraining,
  subscribeTrainingProgress: mockSubscribeTrainingProgress,
}));

import {
  getTrainingFailureAnalytics,
  getTrainingHistory,
  getTrainingRecoveryOptions,
  getTrainingStatus,
  checkTrainingPreflight,
  normalizeTrainingProgress,
  normalizeTrainingRecord,
  resumeTraining,
  startTraining,
  subscribeTrainingProgress,
} from '../services/trainingApi';

describe('trainingApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normalizes snake_case training records', () => {
    const record = normalizeTrainingRecord({
      id: 'task-1',
      model_name: 'demo-model',
      dataset_name: 'demo-dataset',
      method: 'qlora',
      status: 'completed',
      start_time: '2026-04-02T00:00:00',
      end_time: '2026-04-02T00:10:00',
      output_path: '/tmp/output',
      checkpoint_path: '/tmp/output/adapter_model',
      config: {
        model_id: 'demo-model',
        dataset_id: 'demo-dataset',
        learning_rate: 0.0002,
        batch_size: 2,
      },
    });

    expect(record.modelName).toBe('demo-model');
    expect(record.datasetName).toBe('demo-dataset');
    expect(record.startTime).toBe('2026-04-02T00:00:00');
    expect(record.outputPath).toBe('/tmp/output');
    expect(record.checkpointPath).toBe('/tmp/output/adapter_model');
    expect(record.config.modelId).toBe('demo-model');
    expect(record.config.datasetId).toBe('demo-dataset');
    expect(record.config.learningRate).toBe(0.0002);
    expect(record.config.batchSize).toBe(2);
  });

  it('normalizes snake_case training progress', () => {
    const progress = normalizeTrainingProgress({
      epoch: 1,
      step: 12,
      total_steps: 100,
      loss: 0.42,
      lr: 0.0001,
      vram_used: 5.5,
      elapsed_time: 120,
      eta: 30,
      status: 'training',
      message: 'running',
    });

    expect(progress.totalSteps).toBe(100);
    expect(progress.vramUsed).toBe(5.5);
    expect(progress.elapsedTime).toBe(120);
  });

  it('normalizes history responses', async () => {
    mockGetTrainingHistory.mockResolvedValue([
      {
        id: 'task-1',
        model_name: 'demo-model',
        dataset_name: 'demo-dataset',
        method: 'qlora',
        status: 'completed',
        start_time: '2026-04-02T00:00:00',
        output_path: '/tmp/output',
        config: {},
      },
    ]);

    const records = await getTrainingHistory();
    const firstRecord = records[0];

    expect(firstRecord).toBeDefined();
    expect(firstRecord?.modelName).toBe('demo-model');
    expect(firstRecord?.datasetName).toBe('demo-dataset');
    expect(firstRecord?.outputPath).toBe('/tmp/output');
  });

  it('normalizes start and resume responses', async () => {
    mockStartTraining.mockResolvedValue({
      id: 'task-1',
      model_name: 'demo-model',
      dataset_name: 'demo-dataset',
      method: 'qlora',
      status: 'running',
      start_time: '2026-04-02T00:00:00',
      output_path: '/tmp/output',
      config: {},
    });
    mockResumeTraining.mockResolvedValue({
      id: 'task-1',
      model_name: 'demo-model',
      dataset_name: 'demo-dataset',
      method: 'qlora',
      status: 'running',
      start_time: '2026-04-02T00:00:00',
      output_path: '/tmp/output',
      config: {},
    });

    const started = await startTraining({}, { applyRecommendedConfig: true });
    const resumed = await resumeTraining('task-1', 'checkpoint-10');

    expect(mockStartTraining).toHaveBeenCalledWith({}, { applyRecommendedConfig: true });
    expect(started.modelName).toBe('demo-model');
    expect(resumed.datasetName).toBe('demo-dataset');
  });

  it('normalizes training status responses', async () => {
    mockApiClientGet.mockResolvedValue({
      data: {
        is_training: true,
        record: {
          id: 'task-1',
          model_name: 'demo-model',
          dataset_name: 'demo-dataset',
          method: 'qlora',
          status: 'running',
          start_time: '2026-04-02T00:00:00',
          output_path: '/tmp/output',
          config: {},
        },
        progress: {
          epoch: 1,
          step: 10,
          total_steps: 20,
          loss: 0.1,
          lr: 0.0001,
          vram_used: 4.2,
          elapsed_time: 60,
          eta: 30,
          status: 'training',
          message: 'running',
        },
      },
    });

    const status = await getTrainingStatus();

    expect(status.record.modelName).toBe('demo-model');
    expect(status.progress.totalSteps).toBe(20);
    expect(status.progress.vramUsed).toBe(4.2);
  });

  it('normalizes streamed progress events', () => {
    const unsubscribe = vi.fn();
    mockSubscribeTrainingProgress.mockImplementation((handler) => {
      handler({
        epoch: 1,
        step: 5,
        total_steps: 50,
        vram_used: 3.3,
        elapsed_time: 12,
        status: 'training',
      });
      return unsubscribe;
    });

    const onProgress = vi.fn();
    const result = subscribeTrainingProgress(onProgress);

    expect(onProgress).toHaveBeenCalledWith(
      expect.objectContaining({
        totalSteps: 50,
        vramUsed: 3.3,
        elapsedTime: 12,
      }),
    );
    expect(result).toBe(unsubscribe);
  });

  it('requests training preflight with the full config payload', async () => {
    mockApiClientPost.mockResolvedValue({
      data: {
        passed: true,
        status: 'ready',
        summary: 'ok',
        checks: [{ key: 'model', label: '基础模型', status: 'passed', message: 'ok' }],
      },
    });

    const result = await checkTrainingPreflight({
      model_id: 'demo-model',
      dataset_id: 'demo-dataset',
    });

    expect(mockApiClientPost).toHaveBeenCalledWith('/training/preflight', {
      model_id: 'demo-model',
      dataset_id: 'demo-dataset',
    });
    expect(result.status).toBe('ready');
    expect(result.checks[0].key).toBe('model');
  });

  it('normalizes recovery options and failure analytics payloads', async () => {
    mockGetTrainingRecoveryOptions.mockResolvedValue({
      generated_at: '2026-04-16T00:00:00',
      options: [
        {
          task_id: 'task-1',
          status: 'failed',
          model_name: 'demo-model',
          dataset_name: 'demo-dataset',
          start_time: '2026-04-16T00:00:00',
          checkpoints: [{ name: 'checkpoint-100', step: 100 }],
          latest_checkpoint_name: 'checkpoint-100',
          config: { method: 'qlora', batch_size: 1 },
        },
      ],
    });
    mockGetTrainingFailureAnalytics.mockResolvedValue({
      total_runs: 10,
      failed_runs: 2,
      failure_rate_7d: 20,
    });

    const recovery = await getTrainingRecoveryOptions();
    const analytics = await getTrainingFailureAnalytics();

    expect(recovery.options[0].taskId).toBe('task-1');
    expect(recovery.options[0].modelName).toBe('demo-model');
    expect(analytics.totalRuns).toBe(10);
    expect(analytics.failedRuns).toBe(2);
    expect(analytics.failureRate7d).toBe(20);
  });
});
