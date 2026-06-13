import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CloudOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  FolderOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RocketOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  DesktopOutlined,
  ApiOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { Button, Empty, Table, Tag } from 'antd';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';
import { InteractiveButton, GlassHoverCard } from '../components/motion';
import AnimatedLayout from '../components/shared/AnimatedLayout';
import GlassCard from '../components/shared/GlassCard';
import PageHeader from '../components/shared/PageHeader';
import ThemeToggle from '../components/ThemeToggle';
import { CountUp } from '../components/shared/MotionWrapper';
import { getDatasetList, getDeviceInfo, getModelList, listDeploymentPackages } from '../services/api';
import { getTrainingCheckpoints, getTrainingHistory } from '../services/trainingApi';
import { useAppStore } from '../store/appStore';
import type { TrainingRecord } from '../types';
import { useRuntimeContext } from '../runtime/RuntimeContext';
import styles from './Dashboard.module.css';

// 动画配置
const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 12, filter: 'blur(4px)' },
  show: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: {
      duration: 0.4,
      ease: [0.23, 1, 0.32, 1] as const,
    },
  },
};

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
  const [deploymentPackageCount, setDeploymentPackageCount] = useState(0);
  const [latestCheckpoints, setLatestCheckpoints] = useState<Record<string, any>>({});

  const fetchDeviceInfo = async () => {
    if (backendStatus !== 'connected') return;
    try {
      const info = await getDeviceInfo();
      setDeviceInfo(info);
    } catch (error) {
      console.error('Failed to fetch device info:', error);
    }
  };

  useEffect(() => {
    fetchDeviceInfo();
  }, [backendStatus]);

  useEffect(() => {
    if (backendStatus !== 'connected') return;

    const loadChainHealth = async () => {
      try {
        const [modelResult, datasetResult, trainingResult, deploymentResult] =
          await Promise.allSettled([
            getModelList(),
            getDatasetList(),
            getTrainingHistory(),
            listDeploymentPackages(20),
          ]);

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
          const checkpointMap: Record<string, any> = {};
          await Promise.all(
            recent.map(async (record: TrainingRecord) => {
              try {
                const cps = await getTrainingCheckpoints(record.id);
                const validCps = cps.filter((cp: any) => cp.valid !== false);
                if (validCps.length > 0) {
                  checkpointMap[record.id] = validCps[validCps.length - 1];
                }
              } catch {
                // ignore checkpoint load errors
              }
            })
          );
          setLatestCheckpoints(checkpointMap);
        }
        if (deploymentResult.status === 'fulfilled' && Array.isArray(deploymentResult.value)) {
          setDeploymentPackageCount(deploymentResult.value.length);
        }
      } catch (error) {
        console.error('Failed to load chain health:', error);
      }
    };

    void loadChainHealth();
  }, [backendStatus, setDatasets, setModels, setTrainingRecords]);

  const recentTrainings = trainingRecords.slice(-5).reverse();
  const completedTrainings = trainingRecords.filter((record) => record.status === 'completed');
  const evaluationReadyTrainings = completedTrainings.filter(
    (record) => record.adapterPath || record.checkpointPath || record.outputPath,
  );
  const storageReady = summary.storageStatus === 'ready' || summary.storageStatus === 'healthy';
  const storageStatusLabel =
    summary.storageStatus === 'ready' || summary.storageStatus === 'healthy'
      ? '正常'
      : summary.storageStatus === 'degraded'
        ? '降级'
        : summary.storageStatus === 'error'
          ? '异常'
          : '未知';

  const chainSteps = [
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
  ];
  const readyStepCount = chainSteps.filter((step) => step.ready).length;
  const chainHealthPercent = Math.round((readyStepCount / chainSteps.length) * 100);

  // 构建下一步建议
  const suggestions = [];
  if (models.length === 0) {
    suggestions.push({
      title: '没有模型',
      desc: '去模型管理下载/导入模型',
      action: () => navigate('/models'),
      buttonText: '前往模型管理',
      type: 'warning',
    });
  }
  if (datasets.length === 0) {
    suggestions.push({
      title: '没有数据集',
      desc: '去数据集上传，准备微调数据',
      action: () => navigate('/datasets'),
      buttonText: '前往数据集管理',
      type: 'warning',
    });
  }
  if (deviceInfo && !deviceInfo.cuda_available && !deviceInfo.mps_available) {
    suggestions.push({
      title: '无 GPU',
      desc: '训练不可用，但聊天/知识库可继续体验',
      type: 'info',
    });
  }
  if (!inference.ollamaAvailable) {
    suggestions.push({
      title: 'Ollama 未启动',
      desc: '本地推理不可用，可切换 HuggingFace 或查看 Docker Ollama 说明',
      type: 'warning',
    });
  }
  if (suggestions.length === 0) {
    suggestions.push({
      title: '环境就绪',
      desc: '所有基础环境均已就绪，您可以开始训练新模型或进行 AI 对话',
      type: 'success',
    });
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <Tag
            icon={<CheckCircleOutlined />}
            style={{
              borderRadius: 'var(--radius-sm)',
              fontWeight: 600,
              background: 'var(--success-light)',
              borderColor: 'var(--success-border)',
              color: 'var(--success)',
              padding: '2px 8px',
            }}
          >
            完成
          </Tag>
        );
      case 'failed':
        return (
          <Tag
            icon={<CloseCircleOutlined />}
            style={{
              borderRadius: 'var(--radius-sm)',
              fontWeight: 600,
              background: 'var(--error-light)',
              borderColor: 'var(--error-border)',
              color: 'var(--error)',
              padding: '2px 8px',
            }}
          >
            失败
          </Tag>
        );
      case 'stopped':
        return (
          <Tag
            icon={<ExclamationCircleOutlined />}
            style={{
              borderRadius: 'var(--radius-sm)',
              fontWeight: 600,
              background: 'var(--warning-light)',
              borderColor: 'var(--warning-border)',
              color: 'var(--warning)',
              padding: '2px 8px',
            }}
          >
            停止
          </Tag>
        );
      default:
        return (
          <Tag
            icon={<ClockCircleOutlined spin />}
            style={{
              borderRadius: 'var(--radius-sm)',
              fontWeight: 600,
              background: 'var(--info-light)',
              borderColor: 'var(--info-border)',
              color: 'var(--info)',
              padding: '2px 8px',
            }}
          >
            训练中
          </Tag>
        );
    }
  };

  const trainingColumns = [
    {
      title: '模型',
      key: 'model',
      render: (_: unknown, record: TrainingRecord) => {
        const id = record.baseModelId || record.config?.modelId || record.modelName;
        const model = models.find((m) => m.id === id);
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <FolderOutlined style={{ color: 'var(--accent-primary)', fontSize: '16px' }} />
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
              {model?.name || id}
            </span>
          </div>
        );
      },
    },
    {
      title: '数据集',
      key: 'dataset',
      render: (_: unknown, record: TrainingRecord) => {
        const id = record.datasetId || record.config?.datasetId || record.datasetName;
        const dataset = datasets.find((d) => d.id === id);
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <DatabaseOutlined style={{ color: 'var(--accent-secondary)', fontSize: '16px' }} />
            <span style={{ color: 'var(--text-secondary)' }}>{dataset?.name || id}</span>
          </div>
        );
      },
    },
    {
      title: '方法',
      key: 'method',
      render: (_: unknown, record: TrainingRecord) => {
        const method = record.method || record.config?.method || 'qlora';
        return (
          <Tag
            style={{
              borderRadius: 'var(--radius-sm)',
              fontWeight: 600,
              background: method === 'qlora' ? 'var(--success-light)' : 'var(--info-light)',
              borderColor: method === 'qlora' ? 'var(--success)' : 'var(--info)',
              color: method === 'qlora' ? 'var(--success)' : 'var(--info)',
              padding: '2px 8px',
            }}
          >
            {method.toUpperCase()}
          </Tag>
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => getStatusBadge(status),
    },
    {
      title: '时间',
      dataIndex: 'startTime',
      key: 'startTime',
      render: (date: string) => (
        <span
          style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', fontWeight: 500 }}
        >
          {new Date(date).toLocaleString('zh-CN')}
        </span>
      ),
    },
    {
      title: '最新检查点',
      key: 'checkpoint',
      render: (_: unknown, record: TrainingRecord) => {
        const cp = latestCheckpoints[record.id];
        if (!cp) return <span style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>-</span>;
        return (
          <div>
            <Tag
              style={{
                borderRadius: 'var(--radius-sm)',
                fontWeight: 600,
                background: 'var(--accent-primary-light)',
                borderColor: 'var(--accent-primary)',
                color: 'var(--accent-primary)',
              }}
            >
              step {cp.step}
            </Tag>
            {cp.metadata?.loss !== undefined && (
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                loss {cp.metadata.loss.toFixed(4)}
              </div>
            )}
          </div>
        );
      },
    },
  ];

  const mainActions = [
    {
      title: '准备模型',
      icon: <FolderOutlined />,
      color: 'var(--success)', // emerald
      onClick: () => navigate('/models'),
      description: '下载或导入大语言模型，支持 GGUF、Safetensors、PyTorch 等格式。',
    },
    {
      title: '上传数据集',
      icon: <DatabaseOutlined />,
      color: 'var(--warning)', // amber
      onClick: () => navigate('/datasets'),
      description: '上传并分析训练数据集，支持 JSON / JSONL 格式文件。',
    },
    {
      title: '开始训练',
      icon: <RocketOutlined />,
      color: 'var(--accent-primary)', // indigo
      onClick: () => navigate('/training'),
      description: '按问答或结构化输出目标创建微调任务。',
    },
    {
      title: '评估与部署',
      icon: <ApiOutlined />,
      color: 'var(--accent-primary)', // blue
      onClick: () => navigate('/evaluation'),
      description: '对比 base 与微调模型输出，再生成应用接入示例。',
    },
  ];

  const formatValue = (val: number) => Number(val.toFixed(1));
  
  const vramTotal = formatValue(deviceInfo?.vram_total || 0);
  const vramFree = deviceInfo?.vram_free !== undefined ? deviceInfo.vram_free : vramTotal;
  const vramUsed = formatValue(Math.max(0, vramTotal - vramFree));
  const vramPercent = vramTotal > 0 ? Math.min(100, Math.round((vramUsed / vramTotal) * 100)) : 0;

  const memTotal = formatValue(deviceInfo?.memory_total || 0);
  const memFree = deviceInfo?.memory_free !== undefined ? deviceInfo.memory_free : memTotal;
  const memUsed = formatValue(Math.max(0, memTotal - memFree));
  const memPercent = memTotal > 0 ? Math.min(100, Math.round((memUsed / memTotal) * 100)) : 0;

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
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <div>
                  <p
                    style={{
                      fontSize: 'var(--text-lg)',
                      color: 'var(--text-secondary)',
                      marginBottom: 'var(--space-6)',
                    }}
                  >
                    后端服务未连接，请先启动应用以获取实时监控。
                  </p>
                  <Button
                    type="primary"
                    icon={<SettingOutlined />}
                    onClick={() => navigate('/device')}
                    size="large"
                    style={{ borderRadius: 'var(--radius-md)', fontWeight: 600 }}
                  >
                    查看设备状态
                  </Button>
                </div>
              }
            />
          </GlassCard>
        ) : (
          <motion.div variants={containerVariants} initial="hidden" animate="show">
            {/* Bento Grid 硬件与系统监控 */}
            <div className={styles.bentoGrid}>
              
              {/* Card 1: 硬件设备控制台 */}
              <div className={styles['span-6']}>
                <motion.div variants={itemVariants} style={{ height: '100%' }}>
                  <GlassHoverCard className={styles.statCard} tilt3D={true}>
                    <div className={styles.deviceConsole}>
                      <div className={styles.deviceTitleArea}>
                        <span className={styles.sectionTitle} style={{ marginBottom: 0 }}>
                          <DesktopOutlined style={{ color: 'var(--accent-neon-cyan, #00d8a5)' }} />
                          硬件设备控制台
                        </span>
                      </div>
                      
                      <div className={styles.deviceMetricsGrid}>
                        {/* VRAM Meter */}
                        <div className={styles.metricProgressArea}>
                          <div className={styles.metricHeader}>
                            <span className={styles.metricTitle}>GPU 显存占用</span>
                            <span className={styles.metricValue}>
                              <CountUp value={vramUsed} decimals={1} />
                              <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontWeight: 500 }}>
                                 / {vramTotal} GB
                              </span>
                            </span>
                          </div>
                          <div className={styles.metricBarContainer}>
                            <div 
                              className={styles.metricBarFill}
                              style={{ 
                                width: `${vramPercent}%`,
                                background: vramPercent > 90
                                  ? 'linear-gradient(90deg, #ef4444, #f87171)'
                                  : vramPercent > 75
                                    ? 'linear-gradient(90deg, #f59e0b, #fbbf24)'
                                    : 'var(--gradient-brand)',
                                transition: 'width 0.8s ease, background 0.6s ease',
                              }}
                            />
                          </div>
                          <span style={{ fontSize: 11, textAlign: 'right', display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ color: 'var(--text-tertiary)' }}>已占用 {vramPercent}%</span>
                            {vramPercent > 90 && (
                              <span style={{ color: '#ef4444', fontWeight: 600, fontSize: 10, padding: '1px 6px', background: 'rgba(239,68,68,0.12)', borderRadius: 4, border: '1px solid rgba(239,68,68,0.3)' }}>危险</span>
                            )}
                            {vramPercent > 75 && vramPercent <= 90 && (
                              <span style={{ color: '#f59e0b', fontWeight: 600, fontSize: 10, padding: '1px 6px', background: 'rgba(245,158,11,0.12)', borderRadius: 4, border: '1px solid rgba(245,158,11,0.3)' }}>警告</span>
                            )}
                          </span>
                        </div>

                        {/* System Memory Meter */}
                        <div className={styles.metricProgressArea}>
                          <div className={styles.metricHeader}>
                            <span className={styles.metricTitle}>系统内存占用</span>
                            <span className={styles.metricValue}>
                              <CountUp value={memUsed} decimals={1} />
                              <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontWeight: 500 }}>
                                 / {memTotal} GB
                              </span>
                            </span>
                          </div>
                          <div className={styles.metricBarContainer}>
                            <div 
                              className={styles.metricBarFill}
                              style={{ 
                                width: `${memPercent}%`,
                                background: 'var(--accent-secondary)'
                              }}
                            />
                          </div>
                          <span style={{ fontSize: 11, color: 'var(--text-tertiary)', textAlign: 'right' }}>
                            已占用 {memPercent}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </GlassHoverCard>
                </motion.div>
              </div>

              {/* Card 2: 运行服务矩阵 */}
              <div className={styles['span-3']}>
                <motion.div variants={itemVariants} style={{ height: '100%' }}>
                  <GlassHoverCard className={styles.statCard} tilt3D={true}>
                    <div className={styles.servicesMatrix}>
                      <span className={styles.sectionTitle} style={{ marginBottom: 'var(--space-2)' }}>
                        <ApiOutlined style={{ color: 'var(--accent-secondary)' }} />
                        运行服务矩阵
                      </span>
                      <div className={styles.servicesGrid}>
                        {/* Service Item 1: Backend */}
                        <div className={styles.serviceItem}>
                          <span className={styles.serviceName}>
                            <ThunderboltOutlined style={{ fontSize: 12 }} />
                            API 核心服务
                          </span>
                          <div className={styles.serviceStatusArea}>
                            <span className={styles.serviceStatusLabel}>
                              {backendStatus === 'connected' ? '已就绪' : '未连接'}
                            </span>
                            <span className={`${styles.ledIndicator} ${backendStatus === 'connected' ? styles.healthy : styles.error}`} />
                          </div>
                        </div>

                        {/* Service Item 2: Ollama */}
                        <div className={styles.serviceItem}>
                          <span className={styles.serviceName}>
                            <CloudOutlined style={{ fontSize: 12 }} />
                            Ollama 实例
                          </span>
                          <div className={styles.serviceStatusArea}>
                            <span className={styles.serviceStatusLabel}>
                              {inference.ollamaAvailable ? '活跃' : '离线'}
                            </span>
                            <span className={`${styles.ledIndicator} ${inference.ollamaAvailable ? styles.healthy : styles.warning}`} />
                          </div>
                        </div>

                        {/* Service Item 3: Storage */}
                        <div className={styles.serviceItem}>
                          <span className={styles.serviceName}>
                            <DatabaseOutlined style={{ fontSize: 12 }} />
                            存储健康
                          </span>
                          <div className={styles.serviceStatusArea}>
                            <span className={styles.serviceStatusLabel}>
                              {storageStatusLabel}
                            </span>
                            <span className={`${styles.ledIndicator} ${storageReady ? styles.healthy : styles.error}`} />
                          </div>
                        </div>
                      </div>
                    </div>
                  </GlassHoverCard>
                </motion.div>
              </div>

              {/* Card 3: 平台资产仓 */}
              <div className={styles['span-3']}>
                <motion.div variants={itemVariants} style={{ height: '100%' }}>
                  <GlassHoverCard className={styles.statCard} tilt3D={true}>
                    <div className={styles.assetStatusCard}>
                      <span className={styles.sectionTitle}>
                        <FolderOutlined style={{ color: 'var(--warning)' }} />
                        平台资产仓
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                        <div className={styles.assetStats}>
                          <div>
                            <span className={styles.assetTitle}>可用模型</span>
                            <div className={styles.assetMainNumber} style={{ background: 'var(--gradient-brand)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                              <CountUp value={inference.availableModelCount} />
                            </div>
                          </div>
                          <button onClick={() => navigate('/models')} className={styles.assetActionBtn}>
                            管理 <ArrowRightOutlined style={{ fontSize: 10 }} />
                          </button>
                        </div>
                        <div style={{ height: 1, background: 'var(--border-color)' }} />
                        <div className={styles.assetStats}>
                          <div>
                            <span className={styles.assetTitle}>导入数据集</span>
                            <div className={styles.assetMainNumber} style={{ background: 'var(--gradient-warm)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                              <CountUp value={datasets.length} />
                            </div>
                          </div>
                          <button onClick={() => navigate('/datasets')} className={styles.assetActionBtn}>
                            导入 <ArrowRightOutlined style={{ fontSize: 10 }} />
                          </button>
                        </div>
                      </div>
                    </div>
                  </GlassHoverCard>
                </motion.div>
              </div>

            </div>

            {/* 工程闭环健康 - 虚线与流光折线可视化图 */}
            <motion.div variants={itemVariants} style={{ marginBottom: 'var(--space-8)' }}>
              <GlassCard intensity="medium" noHover className={styles.pipelineCard}>
                <div className={styles.historyHeader}>
                  <span className={styles.sectionTitle} style={{ marginBottom: 0 }}>
                    <CheckCircleOutlined style={{ color: 'var(--success)' }} />
                    工程闭环健康
                  </span>
                  <Tag
                    color={chainHealthPercent >= 80 ? 'success' : chainHealthPercent >= 50 ? 'warning' : 'default'}
                    style={{ borderRadius: 'var(--radius-sm)', fontWeight: 700 }}
                  >
                    {readyStepCount}/{chainSteps.length} 节点就绪 ({chainHealthPercent}%)
                  </Tag>
                </div>
                
                <div className={styles.pipelineFlowTrack}>
                  <div className={styles.pipelineLineBackground} />
                  {chainHealthPercent > 0 && <div className={styles.pipelineLaserFlow} />}
                  
                  <div className={styles.pipelineNodes}>
                    {chainSteps.map((step, idx) => {
                      const isReady = step.ready;
                      return (
                        <button
                          key={step.title}
                          type="button"
                          onClick={step.action}
                          className={`${styles.pipelineNode} ${isReady ? styles.nodeReady : styles.nodePending}`}
                        >
                          <div className={styles.nodeIndicator}>
                            {idx + 1}
                            {isReady && <span className={styles.nodeBadge}>✓</span>}
                          </div>
                          <div className={styles.nodeTitle}>{step.title}</div>
                          <div className={styles.nodeValue}>{step.value}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </GlassCard>
            </motion.div>

            {/* 下一步建议 */}
            <div style={{ marginBottom: 'var(--space-8)' }}>
              <h3 className={styles.sectionTitle}>
                <InfoCircleOutlined style={{ color: 'var(--info)' }} />
                下一步建议
              </h3>
              <div className={styles.suggestionsGrid}>
                {suggestions.map((suggestion, index) => {
                  const getIcon = () => {
                    if (suggestion.type === 'warning') return <ExclamationCircleOutlined />;
                    if (suggestion.type === 'success') return <CheckCircleOutlined />;
                    return <InfoCircleOutlined />;
                  };

                  const getColor = () => {
                    if (suggestion.type === 'warning') return 'var(--warning)';
                    if (suggestion.type === 'success') return 'var(--success)';
                    return 'var(--info)';
                  };

                  return (
                    <motion.div variants={itemVariants} key={index} style={{ height: '100%' }}>
                      <GlassCard
                        intensity="low"
                        style={{
                          height: '100%',
                          borderTop: `3px solid ${getColor()}`,
                          padding: '20px',
                        }}
                      >
                        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                          <div style={{ fontSize: 22, color: getColor(), marginTop: 2 }}>
                            {getIcon()}
                          </div>
                          <div style={{ flex: 1 }}>
                            <div
                              style={{
                                fontWeight: 700,
                                color: 'var(--text-primary)',
                                marginBottom: 6,
                                fontSize: 'var(--text-base)',
                              }}
                            >
                              {suggestion.title}
                            </div>
                            <div
                              style={{
                                color: 'var(--text-secondary)',
                                fontSize: '14px',
                                lineHeight: 1.6,
                                marginBottom: suggestion.action ? 16 : 0,
                              }}
                            >
                              {suggestion.desc}
                            </div>
                            {suggestion.action && (
                              <InteractiveButton
                                variant="primary"
                                onClick={suggestion.action}
                                style={{ borderRadius: '6px', fontWeight: 600, padding: '4px 12px', fontSize: '14px', height: '32px' }}
                              >
                                {suggestion.buttonText}
                              </InteractiveButton>
                            )}
                          </div>
                        </div>
                      </GlassCard>
                    </motion.div>
                  );
                })}
              </div>
            </div>

            {/* 主要操作入口 */}
            <div style={{ marginBottom: 'var(--space-8)' }}>
              <h3 className={styles.sectionTitle}>
                <PlayCircleOutlined style={{ color: 'var(--accent-primary)' }} />
                主要操作入口
              </h3>
              <div className={styles.bentoGrid}>
                {mainActions.map((action, index) => (
                  <div key={index} className={styles['span-3']}>
                    <motion.div
                      variants={itemVariants}
                      style={{ height: '100%' }}
                    >
                      <GlassHoverCard
                        className={styles.quickActionCard}
                        onClick={action.onClick}
                        tilt3D={true}
                        style={{
                          '--spotlight-color': `${action.color}15`,
                          '--spotlight-border': `${action.color}35`,
                        } as React.CSSProperties}
                      >
                        <div
                          className={styles.quickActionIcon}
                          style={{
                            background: `${action.color}12`,
                            color: action.color,
                            border: `1px solid ${action.color}25`,
                          }}
                        >
                          {action.icon}
                        </div>
                        <div>
                          <div className={styles.quickActionTitle}>{action.title}</div>
                          <div className={styles.quickActionDesc}>{action.description}</div>
                        </div>
                      </GlassHoverCard>
                    </motion.div>
                  </div>
                ))}
              </div>
            </div>

            {/* 最近训练记录 */}
            <motion.div variants={itemVariants}>
              <GlassCard className={styles.historyCard} intensity="medium" noHover>
                <div className={styles.historyHeader}>
                  <span className={styles.sectionTitle} style={{ marginBottom: 0 }}>
                    <ClockCircleOutlined style={{ color: 'var(--accent-primary)' }} />
                    最近训练
                  </span>
                  <Button
                    type="text"
                    icon={<ArrowRightOutlined />}
                    onClick={() => navigate('/history')}
                    style={{ fontWeight: 600, color: 'var(--accent-primary)' }}
                  >
                    查看全部
                  </Button>
                </div>

                <div className={styles.tableWrapper} style={{ marginTop: 'var(--space-6)' }}>
                  {recentTrainings.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        <div>
                          <p
                            style={{
                              color: 'var(--text-tertiary)',
                              marginBottom: 'var(--space-4)',
                            }}
                          >
                            暂无训练记录
                          </p>
                          <Button
                            type="primary"
                            icon={<PlusOutlined />}
                            onClick={() => navigate('/training')}
                            style={{ borderRadius: 'var(--radius-md)', fontWeight: 600 }}
                          >
                            开始训练
                          </Button>
                        </div>
                      }
                      style={{ padding: 'var(--space-10) 0' }}
                    />
                  ) : (
                    <Table
                      columns={trainingColumns}
                      dataSource={recentTrainings}
                      rowKey="id"
                      pagination={false}
                      size="middle"
                    />
                  )}
                </div>
              </GlassCard>
            </motion.div>
          </motion.div>
        )}
      </div>
    </AnimatedLayout>
  );
}

