import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockNavigate = vi.hoisted(() => vi.fn());
const mockSetIsTraining = vi.hoisted(() => vi.fn());
const mockAddTrainingRecord = vi.hoisted(() => vi.fn());
const mockSetModels = vi.hoisted(() => vi.fn());
const mockSetDatasets = vi.hoisted(() => vi.fn());
const mockGetModelList = vi.hoisted(() => vi.fn());
const mockGetDatasetList = vi.hoisted(() => vi.fn());
const mockNotifySuccess = vi.hoisted(() => vi.fn());
const mockNotifyError = vi.hoisted(() => vi.fn());
const mockNotifyWarning = vi.hoisted(() => vi.fn());
const mockNotifyInfo = vi.hoisted(() => vi.fn());
const mockNotifyEmit = vi.hoisted(() => vi.fn());

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../store/appStore', () => ({
  useAppStore: () => ({
    models: [{ id: 'model-1', name: 'model-1' }],
    datasets: [{ id: 'dataset-1', name: 'dataset-1' }],
    backendStatus: 'connected',
    isTraining: true,
    setIsTraining: mockSetIsTraining,
    addTrainingRecord: mockAddTrainingRecord,
    setModels: mockSetModels,
    setDatasets: mockSetDatasets,
  }),
}));

vi.mock('../services/api', () => ({
  getModelList: mockGetModelList,
  getDatasetList: mockGetDatasetList,
}));

vi.mock('../runtime/RuntimeContext', () => ({
  useRuntimeContext: () => ({
    actions: {
      setTrainingSelection: vi.fn(),
      syncInferenceSelection: vi.fn(),
    },
    derived: {
      trainingSignal: { phase: 'idle' },
      activeBackend: 'huggingface',
      activeModelId: null,
    },
    observed: {
      training: { progressMessage: '' },
    },
  }),
}));

vi.mock('../utils/notify', () => ({
  notify: {
    success: mockNotifySuccess,
    error: mockNotifyError,
    warning: mockNotifyWarning,
    info: mockNotifyInfo,
    emit: mockNotifyEmit,
  },
}));

vi.mock('../services/trainingApi', () => ({
  checkTrainingPreflight: vi.fn().mockResolvedValue({
    passed: true,
    status: 'ready',
    summary: '预检通过',
    checks: [],
    blockers: [],
    available_vram: 8,
    required_vram: 4,
    suggestions: [],
    warnings: [],
    recommended_config: {},
  }),
  checkTrainingResources: vi.fn().mockResolvedValue({
    passed: true,
    available_vram: 8,
    required_vram: 4,
    suggestions: [],
    warnings: [],
    recommended_config: {},
  }),
  getTrainingFailureAnalytics: vi.fn().mockResolvedValue({
    totalRuns: 0,
    failedRuns: 0,
    stoppedRuns: 0,
    completedRuns: 0,
    failureRate: 0,
    failureRate7d: 0,
    failureRate14d: 0,
    failedRuns7d: 0,
    failedRuns14d: 0,
    totalRuns7d: 0,
    totalRuns14d: 0,
    suspectedVramPressureCount: 0,
    longContextFailureCount: 0,
    unquantizedFailureCount: 0,
    topFailedModels: [],
    topFailedDatasets: [],
    topFailedMethods: [],
    recentFailures: [],
  }),
  getTrainingStatus: vi.fn().mockResolvedValue({
    is_training: false,
    record: null,
    progress: {
      epoch: 0,
      step: 0,
      totalSteps: 0,
      loss: 0,
      lr: 0,
      vramUsed: 0,
      elapsedTime: 0,
      eta: 0,
      status: 'idle',
      message: '',
    },
  }),
  getTrainingHistory: vi.fn().mockResolvedValue([]),
  getTrainingCheckpoints: vi.fn().mockResolvedValue([]),
  getTrainingRecoveryOptions: vi.fn().mockResolvedValue({ generatedAt: '', options: [] }),
  getTrainingOverviewV2: vi.fn().mockResolvedValue({
    queue: { queue_size: 0, running_count: 0, max_queue_size: 10 },
    resource_signals: {
      suspected_vram_pressure_count: 0,
      long_context_failure_count: 0,
      unquantized_failure_count: 0,
    },
  }),
  getTrainingTaskMetricsV2: vi.fn().mockResolvedValue({ items: [], next_cursor: 0 }),
  resumeTraining: vi.fn(),
  startTraining: vi.fn(),
  stopTraining: vi.fn(),
  subscribeTrainingProgress: vi.fn(() => () => {}),
  startSwiftTraining: vi.fn(),
}));

vi.mock('../pages/Training/useTrainingEventStreamV2', () => ({
  useTrainingEventStreamV2: ({
    enabled,
    onEvent,
  }: {
    enabled?: boolean;
    onEvent?: (event: any) => void;
  }) => {
    const firedRef = React.useRef(false);
    React.useEffect(() => {
      if (!enabled || !onEvent || firedRef.current) return;
      firedRef.current = true;
      onEvent({
        event_id: 'tev2-1',
        version: 'v2',
        ts: '2026-04-17T00:00:00Z',
        task_id: 'task-1',
        phase: 'queued',
        kind: 'task_queued',
        sequence: 1,
        payload: {
          message: 'Task queued',
          queue_position: 1,
          estimated_wait_seconds: 0,
        },
      });
      onEvent({
        event_id: 'tev2-2',
        version: 'v2',
        ts: '2026-04-17T00:00:02Z',
        task_id: 'task-1',
        phase: 'running',
        kind: 'progress_updated',
        sequence: 2,
        payload: {
          epoch: 1,
          step: 3,
          total_steps: 10,
          loss: 0.3,
          lr: 0.0001,
          vram_used: 4.2,
          elapsed_time: 30,
          status: 'running',
          message: 'Running',
        },
      });
      onEvent({
        event_id: 'tev2-3',
        version: 'v2',
        ts: '2026-04-17T00:00:05Z',
        task_id: 'task-1',
        phase: 'completed',
        kind: 'progress_updated',
        sequence: 3,
        payload: {
          final_loss: 0.12,
          final_lr: 0.00005,
          final_elapsed_time: 100,
          final_steps: 10,
          status: 'completed',
          message: 'Training completed!',
        },
      });
    }, [enabled, onEvent]);

    return {
      connectionState: 'connected',
      lastEvent: null,
      error: null,
      lastSequence: 3,
      lastEventId: 'tev2-3',
    };
  },
}));

vi.mock('../components/shared/AnimatedLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../components/shared/GlassCard', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../components/shared/InsightPanel', () => ({
  default: ({ title, summary }: { title: string; summary?: string }) => (
    <div data-testid={`insight-${title}`}>{summary || title}</div>
  ),
}));

vi.mock('../components/SwiftChecker', () => ({
  default: () => <div data-testid="swift-checker">swift</div>,
}));

vi.mock('../components/TrainingChart', () => ({
  default: () => <div data-testid="training-chart">chart</div>,
}));

vi.mock('../pages/Training/components/ConfigForm', () => ({
  default: () => <div data-testid="config-form">config</div>,
}));

vi.mock('../pages/Training/components/LossChart', () => ({
  default: ({ data }: { data: Array<{ step: number }> }) => (
    <div data-testid="loss-chart">{data.length}</div>
  ),
}));

vi.mock('../pages/Training/components/ProgressPanel', () => ({
  default: ({ status, progress }: { status: string; progress: any }) => (
    <div>
      <div data-testid="progress-status">{status}</div>
      <div data-testid="progress-message">{progress?.message || ''}</div>
    </div>
  ),
}));

import TrainingPage from '../pages/Training';

describe('TrainingPage V2 event flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetModelList.mockResolvedValue([{ id: 'model-1', name: 'model-1' }]);
    mockGetDatasetList.mockResolvedValue([{ id: 'dataset-1', name: 'dataset-1' }]);
  });

  it('applies queued -> running -> completed transitions from V2 events', async () => {
    render(
      <MemoryRouter>
        <TrainingPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('训练完成')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(mockGetModelList).toHaveBeenCalled();
      expect(mockGetDatasetList).toHaveBeenCalled();
      expect(mockSetModels).toHaveBeenCalledWith([{ id: 'model-1', name: 'model-1' }]);
      expect(mockSetDatasets).toHaveBeenCalledWith([{ id: 'dataset-1', name: 'dataset-1' }]);
    });

    expect(mockSetIsTraining).toHaveBeenCalledWith(false);
    expect(mockNotifySuccess).toHaveBeenCalledWith('训练完成');
  });
});
