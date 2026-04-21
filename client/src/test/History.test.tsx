import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
