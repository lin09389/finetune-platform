import { DatabaseOutlined, RocketOutlined } from '@ant-design/icons';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AssetSummaryCard from '../pages/dashboard/AssetSummaryCard';
import DeviceConsoleCard from '../pages/dashboard/DeviceConsoleCard';
import MainActionsGrid from '../pages/dashboard/MainActionsGrid';
import PipelineHealthCard from '../pages/dashboard/PipelineHealthCard';
import ServiceMatrixCard from '../pages/dashboard/ServiceMatrixCard';
import SuggestionsGrid from '../pages/dashboard/SuggestionsGrid';
import TrainingHistoryTable from '../pages/dashboard/TrainingHistoryTable';
import type { ChainStep, MainAction, Suggestion } from '../pages/dashboard/types';
import type { Checkpoint, DatasetInfo, ModelInfo, TrainingRecord } from '../types';

const models = [{ id: 'base-model', name: '基础模型' }] as ModelInfo[];
const datasets = [{ id: 'dataset-1', name: '客服问答集' }] as DatasetInfo[];

const makeRecord = (overrides: Partial<TrainingRecord>): TrainingRecord => ({
  id: 'train-1',
  modelName: 'fallback-model',
  datasetName: 'fallback-dataset',
  baseModelId: 'base-model',
  datasetId: 'dataset-1',
  method: 'qlora',
  status: 'completed',
  startTime: '2026-07-01T10:00:00.000Z',
  config: { modelId: 'base-model', datasetId: 'dataset-1', method: 'qlora' } as TrainingRecord['config'],
  outputPath: 'outputs/train-1',
  ...overrides,
});

describe('Dashboard components', () => {
  describe('ServiceMatrixCard', () => {
    it('renders healthy service labels when all services are ready', () => {
      render(
        <ServiceMatrixCard
          backendConnected
          ollamaAvailable
          storageReady
          storageStatusLabel="正常"
        />,
      );

      expect(screen.getByText('运行服务矩阵')).toBeInTheDocument();
      expect(screen.getByText('已就绪')).toBeInTheDocument();
      expect(screen.getByText('活跃')).toBeInTheDocument();
      expect(screen.getByText('正常')).toBeInTheDocument();
      expect(screen.queryByText('未连接')).not.toBeInTheDocument();
    });

    it('renders degraded service labels when services are down', () => {
      render(
        <ServiceMatrixCard
          backendConnected={false}
          ollamaAvailable={false}
          storageReady={false}
          storageStatusLabel="异常"
        />,
      );

      expect(screen.getByText('未连接')).toBeInTheDocument();
      expect(screen.getByText('离线')).toBeInTheDocument();
      expect(screen.getByText('异常')).toBeInTheDocument();
    });
  });

  describe('TrainingHistoryTable', () => {
    it('renders empty state and routes to training', () => {
      const onGoTraining = vi.fn();
      render(
        <TrainingHistoryTable
          recentTrainings={[]}
          models={models}
          datasets={datasets}
          latestCheckpoints={{}}
          onGoHistory={vi.fn()}
          onGoTraining={onGoTraining}
        />,
      );

      expect(screen.getByText('暂无训练记录')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: /开始训练/ }));
      expect(onGoTraining).toHaveBeenCalledTimes(1);
    });

    it('resolves model/dataset names, status, checkpoint info and routes to history', () => {
      const onGoHistory = vi.fn();
      const records = [
        makeRecord({ id: 'train-1', status: 'completed' }),
        makeRecord({
          id: 'train-2',
          status: 'failed',
          baseModelId: 'unknown-model',
          datasetId: 'unknown-dataset',
        }),
      ];
      const latestCheckpoints: Record<string, Checkpoint> = {
        'train-1': {
          name: 'checkpoint-120',
          path: 'outputs/train-1/checkpoint-120',
          step: 120,
          created: '2026-07-01T11:00:00.000Z',
          metadata: { loss: 0.12345 },
        },
      };

      render(
        <TrainingHistoryTable
          recentTrainings={records}
          models={models}
          datasets={datasets}
          latestCheckpoints={latestCheckpoints}
          onGoHistory={onGoHistory}
          onGoTraining={vi.fn()}
        />,
      );

      // 已知 id 映射到资产名称，未知 id 回退为原始 id
      expect(screen.getByText('基础模型')).toBeInTheDocument();
      expect(screen.getByText('客服问答集')).toBeInTheDocument();
      expect(screen.getByText('unknown-model')).toBeInTheDocument();
      expect(screen.getByText('unknown-dataset')).toBeInTheDocument();

      expect(screen.getByText('完成')).toBeInTheDocument();
      expect(screen.getByText('失败')).toBeInTheDocument();

      // 有检查点的行展示 step + loss，没有检查点的行展示占位符
      expect(screen.getByText('step 120')).toBeInTheDocument();
      expect(screen.getByText('loss 0.1235')).toBeInTheDocument();
      expect(screen.getByText('-')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /查看全部/ }));
      expect(onGoHistory).toHaveBeenCalledTimes(1);
    });
  });

  describe('PipelineHealthCard', () => {
    it('renders ready ratio tag and triggers node action on click', () => {
      const goDevice = vi.fn();
      const chainSteps: ChainStep[] = [
        { title: '后端连接', value: '已就绪', ready: true, action: goDevice },
        { title: '大模型资产', value: '1 个模型', ready: true, action: vi.fn() },
        { title: '快捷部署', value: '0 个包', ready: false, action: vi.fn() },
      ];

      render(
        <PipelineHealthCard chainSteps={chainSteps} readyStepCount={2} chainHealthPercent={67} />,
      );

      expect(screen.getByText('工程闭环健康')).toBeInTheDocument();
      expect(screen.getByText('2/3 节点就绪 (67%)')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /后端连接/ }));
      expect(goDevice).toHaveBeenCalledTimes(1);
    });
  });

  describe('MainActionsGrid', () => {
    it('activates actions by click and keyboard', () => {
      const onTrain = vi.fn();
      const onDataset = vi.fn();
      const actions: MainAction[] = [
        {
          title: '开始训练',
          icon: <RocketOutlined />,
          color: 'var(--accent-primary)',
          onClick: onTrain,
          description: '创建微调任务。',
        },
        {
          title: '上传数据集',
          icon: <DatabaseOutlined />,
          color: 'var(--warning)',
          onClick: onDataset,
          description: '上传训练数据集。',
        },
      ];

      render(<MainActionsGrid actions={actions} />);

      expect(screen.getByText('主要操作入口')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: '开始训练' }));
      expect(onTrain).toHaveBeenCalledTimes(1);

      const datasetCard = screen.getByRole('button', { name: '上传数据集' });
      fireEvent.keyDown(datasetCard, { key: 'Enter' });
      fireEvent.keyDown(datasetCard, { key: ' ' });
      fireEvent.keyDown(datasetCard, { key: 'Escape' });
      expect(onDataset).toHaveBeenCalledTimes(2);
    });
  });

  describe('SuggestionsGrid', () => {
    it('renders action button only for suggestions with an action', () => {
      const goModels = vi.fn();
      const suggestions: Suggestion[] = [
        {
          title: '没有模型',
          desc: '去模型管理下载/导入模型',
          type: 'warning',
          action: goModels,
          buttonText: '前往模型管理',
        },
        { title: '无 GPU', desc: '训练不可用', type: 'info' },
      ];

      render(<SuggestionsGrid suggestions={suggestions} />);

      expect(screen.getByText('下一步建议')).toBeInTheDocument();
      expect(screen.getByText('无 GPU')).toBeInTheDocument();
      expect(screen.getAllByRole('button')).toHaveLength(1);

      fireEvent.click(screen.getByRole('button', { name: /前往模型管理/ }));
      expect(goModels).toHaveBeenCalledTimes(1);
    });
  });

  describe('DeviceConsoleCard', () => {
    it('renders usage percents and danger badge when vram is above 90%', () => {
      render(
        <DeviceConsoleCard
          vramUsed={7.6}
          vramTotal={8}
          vramPercent={95}
          memUsed={8}
          memTotal={16}
          memPercent={50}
        />,
      );

      expect(screen.getByText('硬件设备控制台')).toBeInTheDocument();
      expect(screen.getByText('已占用 95%')).toBeInTheDocument();
      expect(screen.getByText('已占用 50%')).toBeInTheDocument();
      expect(screen.getByText('危险')).toBeInTheDocument();
      expect(screen.queryByText('警告')).not.toBeInTheDocument();
    });
  });

  describe('AssetSummaryCard', () => {
    it('routes to models and datasets from asset actions', () => {
      const onGoModels = vi.fn();
      const onGoDatasets = vi.fn();
      render(
        <AssetSummaryCard
          availableModelCount={2}
          datasetCount={1}
          onGoModels={onGoModels}
          onGoDatasets={onGoDatasets}
        />,
      );

      expect(screen.getByText('平台资产仓')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: /管理/ }));
      expect(onGoModels).toHaveBeenCalledTimes(1);
      fireEvent.click(screen.getByRole('button', { name: /导入/ }));
      expect(onGoDatasets).toHaveBeenCalledTimes(1);
    });
  });
});
