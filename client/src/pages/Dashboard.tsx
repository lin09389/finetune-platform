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
import { Button, Col, Empty, Progress, Row, Table, Tag } from 'antd';
import { motion } from 'framer-motion';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import AnimatedLayout from '../components/shared/AnimatedLayout';
import GlassCard from '../components/shared/GlassCard';
import PageHeader from '../components/shared/PageHeader';
import { CountUp } from '../components/shared/MotionWrapper';
import { getDeviceInfo } from '../services/api';
import { useAppStore } from '../store/appStore';
import { useRuntimeContext } from '../runtime/RuntimeContext';
import styles from './Dashboard.module.css';

interface StatCardProps {
  title: string;
  value: number;
  total?: number;
  suffix?: string;
  prefix?: React.ReactNode;
  color: string;
  icon: React.ReactNode;
  progress?: number;
  delay?: number;
}

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
      ease: [0.16, 1, 0.3, 1] as const,
    },
  },
};

const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  total,
  suffix = '',
  prefix,
  color,
  icon,
  progress,
}) => {
  return (
    <GlassCard className={styles.statCard}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--text-tertiary)',
              marginBottom: 'var(--space-3)',
              fontWeight: 'var(--font-semibold)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}
          >
            {title}
          </div>
          <div className={styles.statValue}>
            {prefix}
            <CountUp value={value} decimals={total ? 1 : 0} />
            {total !== undefined && (
              <span className={styles.statTotal}>
                / {total} {suffix}
              </span>
            )}
            {total === undefined && suffix && <span className={styles.statTotal}>{suffix}</span>}
          </div>
        </div>
        <div
          className={styles.statIcon}
          style={{
            background: color,
            color: '#fff',
            boxShadow: `0 4px 12px ${color}40`,
          }}
        >
          {icon}
        </div>
      </div>

      {progress !== undefined && (
        <div style={{ marginTop: 'var(--space-4)' }}>
          <Progress
            percent={progress}
            strokeColor={color}
            trailColor="var(--border-color)"
            size={{ height: 3 }}
            showInfo={false}
            style={{ margin: 0 }}
          />
          <div
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--text-tertiary)',
              marginTop: 'var(--space-2)',
              textAlign: 'right',
              fontWeight: 'var(--font-medium)',
            }}
          >
            {progress}% 已使用
          </div>
        </div>
      )}
    </GlassCard>
  );
};

export default function Dashboard() {
  const navigate = useNavigate();
  const { backendStatus, deviceInfo, setDeviceInfo, models, datasets, trainingRecords } =
    useAppStore();
  const { inference, knowledge } = useRuntimeContext();

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

  const recentTrainings = trainingRecords.slice(-5).reverse();

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
      type: 'info',
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
      dataIndex: 'modelId',
      key: 'modelId',
      render: (id: string) => {
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
      dataIndex: 'datasetId',
      key: 'datasetId',
      render: (id: string) => {
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
      dataIndex: ['config', 'method'],
      key: 'method',
      render: (method: string) => (
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
          {method?.toUpperCase() || 'QLoRA'}
        </Tag>
      ),
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
  ];

  const mainActions = [
    {
      title: '准备模型',
      icon: <FolderOutlined />,
      color: 'var(--success)',
      onClick: () => navigate('/models'),
      description: '下载或导入大语言模型，支持 GGUF / Safetensors / PyTorch 等格式。',
    },
    {
      title: '上传数据集',
      icon: <DatabaseOutlined />,
      color: 'var(--warning)',
      onClick: () => navigate('/datasets'),
      description: '上传并清洗您的训练数据集，支持 JSONL/CSV 格式文件。',
    },
    {
      title: '开始训练 / 进入聊天',
      icon: <RocketOutlined />,
      color: 'var(--accent-primary)',
      onClick: () => navigate('/training'),
      description: '创建并部署微调任务，或直接与已有模型进行实时对话体验。',
    },
  ];

  return (
    <AnimatedLayout animationKey="dashboard">
      <div className={styles.dashboardContainer}>
        {/* 页面标题 */}
        <PageHeader
          title="运行中控台"
          icon={<DesktopOutlined />}
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
            {/* 环境监控概览 */}
            <Row gutter={[16, 16]} style={{ marginBottom: 'var(--space-8)' }}>
              <Col xs={24} sm={12} lg={4}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="GPU 显存"
                    value={deviceInfo?.vram_free || 0}
                    total={deviceInfo?.vram_total || 0}
                    suffix="GB"
                    color="var(--accent-primary)"
                    icon={<ThunderboltOutlined />}
                    progress={Math.round(
                      (((deviceInfo?.vram_total || 1) - (deviceInfo?.vram_free || 0)) /
                        (deviceInfo?.vram_total || 1)) *
                        100,
                    )}
                  />
                </motion.div>
              </Col>

              <Col xs={24} sm={12} lg={4}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="系统内存"
                    value={deviceInfo?.memory_free || 0}
                    total={deviceInfo?.memory_total || 0}
                    suffix="GB"
                    color="var(--accent-secondary)"
                    icon={<DatabaseOutlined />}
                    progress={Math.round(
                      (((deviceInfo?.memory_total || 1) - (deviceInfo?.memory_free || 0)) /
                        (deviceInfo?.memory_total || 1)) *
                        100,
                    )}
                  />
                </motion.div>
              </Col>

              <Col xs={24} sm={12} lg={4}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="可用模型"
                    value={inference.availableModelCount}
                    color="var(--success)"
                    icon={<FolderOutlined />}
                  />
                </motion.div>
              </Col>

              <Col xs={24} sm={12} lg={4}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="数据集"
                    value={datasets.length}
                    color="var(--warning)"
                    icon={<CloudOutlined />}
                  />
                </motion.div>
              </Col>
              
              <Col xs={24} sm={12} lg={4}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="Ollama"
                    value={inference.ollamaAvailable ? 1 : 0}
                    suffix={inference.ollamaAvailable ? '已启动' : '未启动'}
                    color={inference.ollamaAvailable ? "var(--success)" : "var(--text-tertiary)"}
                    icon={<ApiOutlined />}
                  />
                </motion.div>
              </Col>

              <Col xs={24} sm={12} lg={4}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="知识库 Embedding"
                    value={knowledge.embedderStatus?.loaded ? 1 : 0}
                    suffix={knowledge.embedderStatus?.loaded ? '已加载' : '未加载'}
                    color={knowledge.embedderStatus?.loaded ? "var(--info)" : "var(--text-tertiary)"}
                    icon={<DatabaseOutlined />}
                  />
                </motion.div>
              </Col>
            </Row>

            {/* 下一步建议 */}
            <div style={{ marginBottom: 'var(--space-8)' }}>
              <h3 className={styles.sectionTitle}>
                <InfoCircleOutlined style={{ color: 'var(--info)' }} />
                下一步建议
              </h3>
              <Row gutter={[16, 16]}>
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
                  <Col xs={24} md={12} lg={8} key={index}>
                    <motion.div variants={itemVariants} style={{ height: '100%' }}>
                      <GlassCard
                        intensity="low"
                        style={{
                          height: '100%',
                          borderTop: `3px solid ${getColor()}`,
                          padding: '16px',
                        }}
                      >
                        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                          <div style={{ fontSize: 18, color: getColor(), marginTop: 2 }}>
                            {getIcon()}
                          </div>
                          <div style={{ flex: 1 }}>
                            <div
                              style={{
                                fontWeight: 600,
                                color: 'var(--text-primary)',
                                marginBottom: 4,
                                fontSize: 'var(--text-sm)',
                              }}
                            >
                              {suggestion.title}
                            </div>
                            <div
                              style={{
                                color: 'var(--text-secondary)',
                                fontSize: '13px',
                                lineHeight: 1.5,
                                marginBottom: suggestion.action ? 12 : 0,
                              }}
                            >
                              {suggestion.desc}
                            </div>
                            {suggestion.action && (
                              <Button
                                size="small"
                                onClick={suggestion.action}
                                style={{ borderRadius: 'var(--radius-sm)' }}
                              >
                                {suggestion.buttonText}
                              </Button>
                            )}
                          </div>
                        </div>
                      </GlassCard>
                    </motion.div>
                  </Col>
                )})}
              </Row>
            </div>

            {/* 主要操作入口 */}
            <div style={{ marginBottom: 'var(--space-8)' }}>
              <h3 className={styles.sectionTitle}>
                <PlayCircleOutlined style={{ color: 'var(--accent-primary)' }} />
                主要操作入口
              </h3>
              <Row gutter={[24, 24]}>
                {mainActions.map((action, index) => (
                  <Col xs={24} lg={8} key={index}>
                    <motion.div
                      variants={itemVariants}
                      whileTap={{ scale: 0.98 }}
                      style={{ height: '100%' }}
                    >
                      <GlassCard
                        className={styles.quickActionCard}
                        onClick={action.onClick}
                        intensity="low"
                      >
                        <div
                          className={styles.quickActionIcon}
                          style={{
                            background: `${action.color}18`,
                            color: action.color,
                            border: `1px solid ${action.color}30`,
                          }}
                        >
                          {action.icon}
                        </div>
                        <div>
                          <div className={styles.quickActionTitle}>{action.title}</div>
                          <div className={styles.quickActionDesc}>{action.description}</div>
                        </div>
                      </GlassCard>
                    </motion.div>
                  </Col>
                ))}
              </Row>
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
