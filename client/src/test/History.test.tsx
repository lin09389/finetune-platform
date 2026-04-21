import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import History from '../pages/History';

const mockUseAppStore = vi.hoisted(() => vi.fn());
const mockGetTrainingHistory = vi.hoisted(() => vi.fn());
const mockGetTrainingCheckpoints = vi.hoisted(() => vi.fn());
const mockGetTrainingTaskMetricsV2 = vi.hoisted(() => vi.fn());
const mockResumeTraining = vi.hoisted(() => vi.fn());
const mockMergeLora = vi.hoisted(() => vi.fn());
const messageSuccess = vi.hoisted(() => vi.fn());
const messageError = vi.hoisted(() => vi.fn());
const messageWarning = vi.hoisted(() => vi.fn());

vi.mock('../store/appStore', () => ({
  useAppStore: mockUseAppStore,
}));

vi.mock('../services/api', () => ({
  mergeLora: mockMergeLora,
}));

vi.mock('../services/trainingApi', () => ({
  getTrainingHistory: mockGetTrainingHistory,
  getTrainingCheckpoints: mockGetTrainingCheckpoints,
  getTrainingTaskMetricsV2: mockGetTrainingTaskMetricsV2,
  resumeTraining: mockResumeTraining,
}));

vi.mock('antd', async () => {
  const actual = (await vi.importActual('antd')) as Record<string, any>;
  return {
    ...actual,
    message: {
      success: messageSuccess,
      error: messageError,
      warning: messageWarning,
    },
  };
});

describe('History page', () => {
  const mockSetTrainingRecords = vi.fn();
  const mockRemoveTrainingRecord = vi.fn();
  const mockSetIsTraining = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();

    mockUseAppStore.mockReturnValue({
      trainingRecords: [
        {
          id: 'task-1',
          modelName: 'demo-model',
          datasetName: 'demo-dataset',
          method: 'qlora',
          status: 'completed',
          startTime: '2026-04-02T00:00:00',
          endTime: '2026-04-02T00:05:00',
          outputPath: '/tmp/output',
          checkpointPath: '/tmp/output/lora_adapter',
          config: {
            modelId: 'demo-model',
            rank: 8,
            alpha: 16,
            learningRate: 0.0002,
            epochs: 3,
            batchSize: 2,
          },
        },
        {
          id: 'task-2',
          modelName: 'demo-model',
          datasetName: 'demo-dataset-v2',
          method: 'lora',
          status: 'completed',
          startTime: '2026-04-02T01:00:00',
          endTime: '2026-04-02T01:04:00',
          outputPath: '/tmp/output-2',
          checkpointPath: '/tmp/output-2/lora_adapter',
          finalLoss: 0.22,
          elapsedTime: 240,
          totalSteps: 20,
          config: {
            modelId: 'demo-model',
            rank: 16,
            alpha: 32,
            learningRate: 0.0001,
            epochs: 3,
            batchSize: 2,
          },
        },
      ],
      setTrainingRecords: mockSetTrainingRecords,
      removeTrainingRecord: mockRemoveTrainingRecord,
      setIsTraining: mockSetIsTraining,
    });

    mockGetTrainingHistory.mockResolvedValue([
      {
        id: 'task-1',
        modelName: 'demo-model',
        datasetName: 'demo-dataset',
        method: 'qlora',
        status: 'completed',
        startTime: '2026-04-02T00:00:00',
        endTime: '2026-04-02T00:05:00',
        outputPath: '/tmp/output',
        checkpointPath: '/tmp/output/lora_adapter',
        config: { modelId: 'demo-model' },
      },
      {
        id: 'task-2',
        modelName: 'demo-model',
        datasetName: 'demo-dataset-v2',
        method: 'lora',
        status: 'completed',
        startTime: '2026-04-02T01:00:00',
        endTime: '2026-04-02T01:04:00',
        outputPath: '/tmp/output-2',
        checkpointPath: '/tmp/output-2/lora_adapter',
        finalLoss: 0.22,
        elapsedTime: 240,
        totalSteps: 20,
        config: { modelId: 'demo-model' },
      },
    ]);

    mockGetTrainingCheckpoints.mockResolvedValue([
      {
        name: 'checkpoint-10',
        path: '/tmp/output/checkpoints/checkpoint-10',
        step: 10,
        created: '2026-04-02T00:03:00',
      },
    ]);

    mockResumeTraining.mockResolvedValue({
      id: 'task-1',
      modelName: 'demo-model',
      datasetName: 'demo-dataset',
      method: 'qlora',
      status: 'running',
      startTime: '2026-04-02T00:00:00',
      outputPath: '/tmp/output',
      config: {},
    });
    mockMergeLora.mockResolvedValue({
      status: 'success',
      path: '/tmp/outputs/exports/demo-model-merged',
    });
    mockGetTrainingTaskMetricsV2.mockImplementation((taskId: string) =>
      Promise.resolve({
        task_id: taskId,
        cursor: 0,
        next_cursor: 2,
        has_more: false,
        items:
          taskId === 'task-1'
            ? [
                { step: 1, loss: 0.42 },
                { step: 10, loss: 0.18 },
              ]
            : [
                { step: 1, loss: 0.5 },
                { step: 20, loss: 0.22 },
              ],
      }),
    );
  });

  it('loads history records on mount', async () => {
    render(<History />);

    await waitFor(() => {
      expect(mockGetTrainingHistory).toHaveBeenCalled();
      expect(mockSetTrainingRecords).toHaveBeenCalled();
    });
  });

  it('can render as the training comparison module', async () => {
    render(<History mode="compare" />);

    expect(screen.getByText('训练对比')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockGetTrainingHistory).toHaveBeenCalled();
    });
  });

  it('preselects comparable recent records when rendered as the training comparison module', async () => {
    const records = [
      {
        id: 'task-running',
        modelName: 'running-model',
        datasetName: 'running-dataset',
        method: 'qlora',
        status: 'running',
        startTime: '2026-04-05T00:00:00',
        outputPath: '/tmp/running-output',
        finalLoss: 0.11,
        config: { modelId: 'running-model' },
      },
      {
        id: 'task-failed',
        modelName: 'failed-model',
        datasetName: 'failed-dataset',
        method: 'qlora',
        status: 'failed',
        startTime: '2026-04-04T00:00:00',
        outputPath: '/tmp/failed-output',
        finalLoss: 0.2,
        config: { modelId: 'failed-model' },
      },
      {
        id: 'task-plain',
        modelName: 'plain-model',
        datasetName: 'plain-dataset',
        method: 'lora',
        status: 'completed',
        startTime: '2026-04-03T00:00:00',
        endTime: '2026-04-03T00:04:00',
        outputPath: '',
        config: { modelId: 'plain-model' },
      },
      {
        id: 'task-stopped',
        modelName: 'stopped-model',
        datasetName: 'stopped-dataset',
        method: 'lora',
        status: 'stopped',
        startTime: '2026-04-02T00:00:00',
        endTime: '2026-04-02T00:03:00',
        outputPath: '/tmp/stopped-output',
        totalSteps: 30,
        config: { modelId: 'stopped-model' },
      },
      {
        id: 'task-completed',
        modelName: 'completed-model',
        datasetName: 'completed-dataset',
        method: 'qlora',
        status: 'completed',
        startTime: '2026-04-01T00:00:00',
        endTime: '2026-04-01T00:05:00',
        outputPath: '/tmp/completed-output',
        finalLoss: 0.18,
        config: { modelId: 'completed-model' },
      },
    ];

    mockUseAppStore.mockReturnValue({
      trainingRecords: records,
      setTrainingRecords: mockSetTrainingRecords,
      removeTrainingRecord: mockRemoveTrainingRecord,
      setIsTraining: mockSetIsTraining,
    });
    mockGetTrainingHistory.mockResolvedValue(records);

    render(<History mode="compare" />);

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /移出对比/ })).toHaveLength(2);
    });

    expect(screen.getByRole('button', { name: /对比训练/ })).toBeEnabled();
    expect(
      within(screen.getByText('stopped-dataset').closest('tr') as HTMLElement).getByRole(
        'button',
        { name: /移出对比/ },
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByText('completed-dataset').closest('tr') as HTMLElement).getByRole(
        'button',
        { name: /移出对比/ },
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByText('running-dataset').closest('tr') as HTMLElement).getByRole(
        'button',
        { name: /加入对比/ },
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByText('failed-dataset').closest('tr') as HTMLElement).getByRole('button', {
        name: /加入对比/,
      }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByText('plain-dataset').closest('tr') as HTMLElement).getByRole('button', {
        name: /加入对比/,
      }),
    ).toBeInTheDocument();
  });

  it('loads checkpoints when opening record detail', async () => {
    render(<History />);

    fireEvent.click(screen.getAllByRole('button', { name: /详情/ })[0]!);

    await waitFor(() => {
      expect(mockGetTrainingCheckpoints).toHaveBeenCalledWith('task-1');
      expect(screen.getByText(/checkpoint-10/i)).toBeInTheDocument();
    });
  });

  it('resumes training from a checkpoint', async () => {
    render(<History />);

    fireEvent.click(screen.getAllByRole('button', { name: /详情/ })[0]!);

    expect(await screen.findByText(/checkpoint-10/i, {}, { timeout: 10000 })).toBeInTheDocument();

    const resumeButton = await screen.findByRole(
      'button',
      { name: /恢复训练|resume/i },
      { timeout: 10000 },
    );
    fireEvent.click(resumeButton);

    await waitFor(
      () => {
        expect(mockResumeTraining).toHaveBeenCalledWith('task-1', 'checkpoint-10');
        expect(mockSetIsTraining).toHaveBeenCalledWith(true);
        expect(messageSuccess).toHaveBeenCalled();
      },
      { timeout: 10000 },
    );
  }, 15000);

  it('merges and exports a LoRA adapter from record detail', async () => {
    render(<History />);

    fireEvent.click(screen.getAllByRole('button', { name: /详情/ })[0]!);

    const mergeButton = await screen.findByRole(
      'button',
      { name: /合并导出/ },
      { timeout: 10000 },
    );
    fireEvent.click(mergeButton);

    const confirmButton = await screen.findByRole(
      'button',
      { name: /开始合并/ },
      { timeout: 10000 },
    );
    fireEvent.click(confirmButton);

    await waitFor(
      () => {
        expect(mockMergeLora).toHaveBeenCalledWith('demo-model', {
          adapter_path: '/tmp/output/lora_adapter',
          training_id: 'task-1',
          output_name: 'demo-model-merged',
        });
        expect(messageSuccess).toHaveBeenCalledWith('合并导出已提交');
      },
      { timeout: 10000 },
    );
  }, 15000);

  it('compares two training records with metric curves and config differences', async () => {
    render(<History />);

    const addButtons = screen.getAllByRole('button', { name: /加入对比/ });
    fireEvent.click(addButtons[0]!);
    fireEvent.click(addButtons[1]!);

    fireEvent.click(screen.getByRole('button', { name: /对比训练/ }));

    await waitFor(
      () => {
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-1', 0, 1000);
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-2', 0, 1000);
      },
      { timeout: 10000 },
    );

    expect(await screen.findByText('训练对比', {}, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getByText('Loss 曲线')).toBeInTheDocument();
    expect(screen.getByText('关键配置差异')).toBeInTheDocument();
    expect(screen.getAllByText('demo-dataset-v2').length).toBeGreaterThan(0);
  }, 15000);

  it('loads all metric pages before rendering comparison curves', async () => {
    mockGetTrainingTaskMetricsV2.mockImplementation((taskId: string, cursor: number) =>
      Promise.resolve(
        taskId === 'task-1' && cursor === 0
          ? {
              task_id: taskId,
              cursor,
              next_cursor: 1,
              has_more: true,
              items: [{ step: 1, loss: 0.42 }],
            }
          : {
              task_id: taskId,
              cursor,
              next_cursor: cursor + 1,
              has_more: false,
              items: [{ step: cursor + 2, loss: taskId === 'task-1' ? 0.18 : 0.22 }],
            },
      ),
    );

    render(<History />);

    const addButtons = screen.getAllByRole('button', { name: /加入对比/ });
    fireEvent.click(addButtons[0]!);
    fireEvent.click(addButtons[1]!);
    fireEvent.click(screen.getByRole('button', { name: /对比训练/ }));

    await waitFor(
      () => {
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-1', 0, 1000);
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-1', 1, 1000);
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-2', 0, 1000);
      },
      { timeout: 10000 },
    );
  }, 15000);

  it('exports the selected comparison as a markdown report', async () => {
    render(<History />);

    const addButtons = screen.getAllByRole('button', { name: /加入对比/ });
    fireEvent.click(addButtons[0]!);
    fireEvent.click(addButtons[1]!);
    fireEvent.click(screen.getByRole('button', { name: /对比训练/ }));

    await waitFor(
      () => {
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-1', 0, 1000);
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-2', 0, 1000);
      },
      { timeout: 10000 },
    );

    const exportButton = await screen.findByRole(
      'button',
      { name: /导出报告/ },
      { timeout: 10000 },
    );
    fireEvent.click(exportButton);

    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(messageSuccess).toHaveBeenCalledWith(expect.stringContaining('对比报告已导出'));
  }, 15000);

  it('exports the selected comparison as a csv report', async () => {
    render(<History />);

    const addButtons = screen.getAllByRole('button', { name: /加入对比/ });
    fireEvent.click(addButtons[0]!);
    fireEvent.click(addButtons[1]!);
    fireEvent.click(screen.getByRole('button', { name: /对比训练/ }));

    await waitFor(
      () => {
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-1', 0, 1000);
        expect(mockGetTrainingTaskMetricsV2).toHaveBeenCalledWith('task-2', 0, 1000);
      },
      { timeout: 10000 },
    );

    const exportButton = await screen.findByRole(
      'button',
      { name: /导出 CSV/ },
      { timeout: 10000 },
    );
    fireEvent.click(exportButton);

    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(messageSuccess).toHaveBeenCalledWith(expect.stringContaining('CSV 已导出'));
  }, 15000);
});
