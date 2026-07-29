import {
  ApiOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  FolderOutlined,
  RocketOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { motion } from 'framer-motion';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';
import { useMotionConfig } from '../components/motion';
import AnimatedLayout from '../components/shared/AnimatedLayout';
import GlassCard from '../components/shared/GlassCard';
import PageHeader from '../components/shared/PageHeader';
import StatusState from '../components/shared/StatusState';
import ThemeToggle from '../components/ThemeToggle';
import { getDatasetList, getDeviceInfo, getModelList, listDeploymentPackages } from '../services/api';
import { getTrainingCheckpoints, getTrainingHistory } from '../services/trainingApi';
import { useAppStore } from '../store/appStore';
import { staggerContainer } from '../theme/motion-tokens';
import type { Checkpoint, TrainingRecord } from '../types';
import { useRuntimeContext } from '../runtime/RuntimeContext';
import styles from './Dashboard.module.css';
import AssetSummaryCard from './dashboard/AssetSummaryCard';
import DeviceConsoleCard from './dashboard/DeviceConsoleCard';
import MainActionsGrid from './dashboard/MainActionsGrid';
import PipelineHealthCard from './dashboard/PipelineHealthCard';
import ServiceMatrixCard from './dashboard/ServiceMatrixCard';
import SuggestionsGrid from './dashboard/SuggestionsGrid';
import TrainingHistoryTable from './dashboard/TrainingHistoryTable';
import type { ChainStep, MainAction, Suggestion } from './dashboard/types';

export default function Dashboard() {
  const navigate = useNavigate();
  const {
    backendStatus,
    deviceInfo,
    setDeviceInfo,
    models,
    datasets,
    trainingRecords,
    setModels,
    setDatasets,
    setTrainingRecords,
  } = useAppStore(useShallow(state => ({
    backendStatus: state.backendStatus,
    deviceInfo: state.deviceInfo,
    setDeviceInfo: state.setDeviceInfo,
    models: state.models,
    datasets: state.datasets,
    trainingRecords: state.trainingRecords,
    setModels: state.setModels,
    setDatasets: state.setDatasets,
    setTrainingRecords: state.setTrainingRecords
  })));
  const { inference, summary } = useRuntimeContext();
  const { getSafeVariants } = useMotionConfig();
  const [deploymentPackageCount, setDeploymentPackageCount] = useState(0);
  const [latestCheckpoints, setLatestCheckpoints] = useState<Record<string, Checkpoint>>({});

  const fetchDeviceInfo = useCallback(async () => {
    if (backendStatus !== 'connected') return;
    try {
      const info = await getDeviceInfo();
      setDeviceInfo(info);
    } catch {
      // Device status is also represented by backendStatus; keep dashboard usable.
    }
  }, [backendStatus, setDeviceInfo]);

  useEffect(() => {
    void fetchDeviceInfo();
  }, [fetchDeviceInfo]);

  useEffect(() => {
    if (backendStatus !== 'connected') return;
    // 卸载/重连后丢弃在途结果，避免向已卸载组件 setState
    let cancelled = false;

    const loadChainHealth = async () => {
      try {
        const [modelResult, datasetResult, trainingResult, deploymentResult] =
          await Promise.allSettled([
            getModelList(),
            getDatasetList(),
            getTrainingHistory(),
            listDeploymentPackages(20),
          ]);
        if (cancelled) return;

        if (modelResult.status === 'fulfilled' && Array.isArray(modelResult.value)) {
          setModels(modelResult.value);
        }
        if (datasetResult.status === 'fulfilled' && Array.isArray(datasetResult.value)) {
          setDatasets(datasetResult.value);
        }
        if (trainingResult.status === 'fulfilled' && Array.isArray(trainingResult.value)) {
          setTrainingRecords(trainingResult.value);
          // 加载最近 5 条训练记录的检查点
          const recent = trainingResult.value.slice(-5).reverse();
          const checkpointMap: Record<string, Checkpoint> = {};
          await Promise.all(
            recent.map(async (record: TrainingRecord) => {
              try {
                const cps = (await getTrainingCheckpoints(record.id)) as Checkpoint[];
                const validCps = cps.filter((cp) => cp.valid !== false);
                if (validCps.length > 0) {
                  const latest = validCps[validCps.length - 1];
                  if (latest) checkpointMap[record.id] = latest;
                }
              } catch {
                // ignore checkpoint load errors
              }
            })
          );
          if (!cancelled) setLatestCheckpoints(checkpointMap);
        }
        if (deploymentResult.status === 'fulfilled' && Array.isArray(deploymentResult.value)) {
          setDeploymentPackageCount(deploymentResult.value.length);
        }
      } catch {
        if (!cancelled) setDeploymentPackageCount(0);
      }
    };

    void loadChainHealth();
    return () => {
      cancelled = true;
    };
  }, [backendStatus, setDatasets, setModels, setTrainingRecords]);

  const { recentTrainings, completedTrainings, evaluationReadyTrainings } = useMemo(() => {
    const completed = trainingRecords.filter((record) => record.status === 'completed');
    return {
      recentTrainings: trainingRecords.slice(-5).reverse(),
      completedTrainings: completed,
      evaluationReadyTrainings: completed.filter(
        (record) => record.adapterPath || record.checkpointPath || record.outputPath,
      ),
    };
  }, [trainingRecords]);

  const storageReady = summary.storageStatus === 'ready' || summary.storageStatus === 'healthy';
  const storageStatusLabel = storageReady
    ? '正常'
    : summary.storageStatus === 'degraded'
      ? '降级'
      : summary.storageStatus === 'error'
        ? '异常'
        : '未知';

  const chainSteps = useMemo<ChainStep[]>(() => [
    {
      title: '后端连接',
      value: backendStatus === 'connected' ? '已就绪' : '未就绪',
      ready: backendStatus === 'connected',
      action: () => navigate('/device'),
    },
    {
      title: '大模型资产',
      value: `${Math.max(models.length, inference.availableModelCount)} 个模型`,
      ready: models.length > 0 || inference.availableModelCount > 0,
      action: () => navigate('/models'),
    },
    {
      title: '数据集就绪',
      value: `${datasets.length} 个数据集`,
      ready: datasets.length > 0,
      action: () => navigate('/datasets'),
    },
    {
      title: '微调训练',
      value: `${completedTrainings.length} 次成功`,
      ready: completedTrainings.length > 0,
      action: () => navigate('/history'),
    },
    {
      title: '评估与对比',
      value: `${evaluationReadyTrainings.length} 个产物`,
      ready: evaluationReadyTrainings.length > 0,
      action: () => navigate('/evaluation'),
    },
    {
      title: '快捷部署',
      value: `${deploymentPackageCount} 个包`,
      ready: deploymentPackageCount > 0,
      action: () => navigate('/deployment'),
    },
  ], [
    backendStatus,
    models.length,
    inference.availableModelCount,
    datasets.length,
    completedTrainings.length,
    evaluationReadyTrainings.length,
    deploymentPackageCount,
    navigate,
  ]);
  const readyStepCount = chainSteps.filter((step) => step.ready).length;
  const chainHealthPercent = Math.round((readyStepCount / chainSteps.length) * 100);

  // 构建下一步建议
  const suggestions = useMemo<Suggestion[]>(() => {
    const items: Suggestion[] = [];
    if (models.length === 0) {
      items.push({
        title: '没有模型',
        desc: '去模型管理下载/导入模型',
        action: () => navigate('/models'),
        buttonText: '前往模型管理',
        type: 'warning',
      });
    }
    if (datasets.length === 0) {
      items.push({
        title: '没有数据集',
        desc: '去数据集上传，准备微调数据',
        action: () => navigate('/datasets'),
        buttonText: '前往数据集管理',
        type: 'warning',
      });
    }
    if (deviceInfo && !deviceInfo.cuda_available && !deviceInfo.mps_available) {
      items.push({
        title: '无 GPU',
        desc: '训练不可用，但聊天/知识库可继续体验',
        type: 'info',
      });
    }
    if (!inference.ollamaAvailable) {
      items.push({
        title: 'Ollama 未启动',
        desc: '本地推理不可用，可切换 HuggingFace 或查看 Docker Ollama 说明',
        type: 'warning',
      });
    }
    if (items.length === 0) {
      items.push({
        title: '环境就绪',
        desc: '所有基础环境均已就绪，您可以开始训练新模型或进行 AI 对话',
        type: 'success',
      });
    }
    return items;
  }, [models.length, datasets.length, deviceInfo, inference.ollamaAvailable, navigate]);

  const mainActions = useMemo<MainAction[]>(() => [
    {
      title: '准备模型',
      icon: <FolderOutlined />,
      color: 'var(--success)',
      onClick: () => navigate('/models'),
      description: '下载或导入大语言模型，支持 GGUF、Safetensors、PyTorch 等格式。',
    },
    {
      title: '上传数据集',
      icon: <DatabaseOutlined />,
      color: 'var(--warning)',
      onClick: () => navigate('/datasets'),
      description: '上传并分析训练数据集，支持 JSON / JSONL 格式文件。',
    },
    {
      title: '开始训练',
      icon: <RocketOutlined />,
      color: 'var(--accent-primary)',
      onClick: () => navigate('/training'),
      description: '按问答或结构化输出目标创建微调任务。',
    },
    {
      title: '评估与部署',
      icon: <ApiOutlined />,
      color: 'var(--accent-primary)',
      onClick: () => navigate('/evaluation'),
      description: '对比 base 与微调模型输出，再生成应用接入示例。',
    },
  ], [navigate]);

  const formatValue = (val: number) => Number(val.toFixed(1));

  const vramTotal = formatValue(deviceInfo?.vram_total || 0);
  const vramFree = deviceInfo?.vram_free !== undefined ? deviceInfo.vram_free : vramTotal;
  const vramUsed = formatValue(Math.max(0, vramTotal - vramFree));
  const vramPercent = vramTotal > 0 ? Math.min(100, Math.round((vramUsed / vramTotal) * 100)) : 0;

  const memTotal = formatValue(deviceInfo?.memory_total || 0);
  const memFree = deviceInfo?.memory_free !== undefined ? deviceInfo.memory_free : memTotal;
  const memUsed = formatValue(Math.max(0, memTotal - memFree));
  const memPercent = memTotal > 0 ? Math.min(100, Math.round((memUsed / memTotal) * 100)) : 0;

  const goModels = useCallback(() => navigate('/models'), [navigate]);
  const goDatasets = useCallback(() => navigate('/datasets'), [navigate]);
  const goHistory = useCallback(() => navigate('/history'), [navigate]);
  const goTraining = useCallback(() => navigate('/training'), [navigate]);

  return (
    <AnimatedLayout animationKey="dashboard">
      <div className={styles.dashboardContainer}>
        {/* 页面标题 */}
        <PageHeader
          title="运行中控台"
          icon={<DesktopOutlined />}
          extraActions={<ThemeToggle />}
          helpTooltip="环境状态监控与微调工作台入口，指引您完成 AI 应用部署。"
        />

        {backendStatus !== 'connected' ? (
          <GlassCard
            intensity="high"
            style={{ textAlign: 'center', padding: 'var(--space-12) var(--space-6)' }}
          >
            <StatusState
              tone="offline"
              title="后端服务未连接"
              description="运行中控台无法读取实时监控。启动本地服务后，可在设备状态页确认连接并继续。"
              action={{
                text: '查看设备状态',
                onClick: () => navigate('/device'),
                icon: <SettingOutlined />,
              }}
            />
          </GlassCard>
        ) : (
          <motion.div variants={getSafeVariants(staggerContainer)} initial="initial" animate="animate">
            {/* Bento Grid 硬件与系统监控 */}
            <div className={styles.bentoGrid}>
              <div className={styles['span-6']}>
                <DeviceConsoleCard
                  vramUsed={vramUsed}
                  vramTotal={vramTotal}
                  vramPercent={vramPercent}
                  memUsed={memUsed}
                  memTotal={memTotal}
                  memPercent={memPercent}
                />
              </div>
              <div className={styles['span-3']}>
                <ServiceMatrixCard
                  backendConnected={backendStatus === 'connected'}
                  ollamaAvailable={inference.ollamaAvailable}
                  storageReady={storageReady}
                  storageStatusLabel={storageStatusLabel}
                />
              </div>
              <div className={styles['span-3']}>
                <AssetSummaryCard
                  availableModelCount={inference.availableModelCount}
                  datasetCount={datasets.length}
                  onGoModels={goModels}
                  onGoDatasets={goDatasets}
                />
              </div>
            </div>

            <PipelineHealthCard
              chainSteps={chainSteps}
              readyStepCount={readyStepCount}
              chainHealthPercent={chainHealthPercent}
            />

            <SuggestionsGrid suggestions={suggestions} />

            <MainActionsGrid actions={mainActions} />

            <TrainingHistoryTable
              recentTrainings={recentTrainings}
              models={models}
              datasets={datasets}
              latestCheckpoints={latestCheckpoints}
              onGoHistory={goHistory}
              onGoTraining={goTraining}
            />
          </motion.div>
        )}
      </div>
    </AnimatedLayout>
  );
}
