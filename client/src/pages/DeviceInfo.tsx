import {
  AppleOutlined,
  CheckCircleOutlined,
  DesktopOutlined,
  InfoCircleOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { Button, Col, Progress, Row, Spin, Tag } from 'antd';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import AnimatedLayout from '../components/shared/AnimatedLayout';
import GlassCard from '../components/shared/GlassCard';
import PageHeader from '../components/shared/PageHeader';
import { getDeviceInfo } from '../services/api';
import { useAppStore } from '../store/appStore';
import styles from './DeviceInfo.module.css';

// 动画配置
const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 15, filter: 'blur(4px)' },
  show: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const },
  },
};

export default function DeviceInfo() {
  const { backendStatus, deviceInfo, setDeviceInfo } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchInfo = async () => {
    if (backendStatus !== 'connected') {
      setError('后端服务未连接');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const info = await getDeviceInfo();
      setDeviceInfo(info);
    } catch (err: any) {
      setError(err.message || '获取设备信息失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInfo();
  }, [backendStatus]);

  const getPlatformIcon = (platform: string) => {
    switch (platform) {
      case 'cuda':
        return <ThunderboltOutlined style={{ color: 'var(--success)' }} />;
      case 'mac':
        return <AppleOutlined style={{ color: 'var(--text-primary)' }} />;
      default:
        return <QuestionCircleOutlined style={{ color: 'var(--text-tertiary)' }} />;
    }
  };

  const getPlatformName = (platform: string) => {
    switch (platform) {
      case 'cuda':
        return 'NVIDIA CUDA';
      case 'mac':
        return 'Apple Silicon (MLX)';
      default:
        return '未知平台';
    }
  };

  const getVramSuggestion = (freeVram: number) => {
    if (freeVram < 6) {
      return {
        title: '显存不足',
        desc: '当前显存小于 6GB，建议使用 INT4 量化 + QLoRA。推荐模型：Qwen2.5-0.5B, Phi-3-mini',
        type: 'warning',
      };
    }
    if (freeVram >= 6 && freeVram < 10) {
      return {
        title: '显存适中',
        desc: '6-10GB 可用 INT4 微调 7B 模型，如 Qwen2.5-1.8B, Llama3-8B, ChatGLM3-6B',
        type: 'info',
      };
    }
    if (freeVram >= 10 && freeVram < 16) {
      return {
        title: '显存充裕',
        desc: '10-16GB 可微调 7B 模型（INT4/INT8），或用 QLoRA 微调 13B 模型',
        type: 'success',
      };
    }
    return {
      title: '显存充足',
      desc: '16GB+ 可微调 13B 模型，或用 LoRA 微调 30B+ 模型',
      type: 'success',
    };
  };

  if (loading && !deviceInfo) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <AnimatedLayout animationKey="device-info">
      <div className={styles.container}>
        <PageHeader
          title="设备状态"
          icon={<DesktopOutlined />}
          helpTooltip="实时监控 GPU 显存与系统资源，以确保模型微调任务能够顺利运行。"
          primaryAction={
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchInfo}
              loading={loading}
              type="primary"
              style={{ borderRadius: 8 }}
            >
              刷新状态
            </Button>
          }
          style={{ marginBottom: 0 }}
        />

        {error && (
          <motion.div initial="hidden" animate="show" variants={itemVariants}>
            <div
              style={{
                padding: '16px 20px',
                background: 'var(--error-light)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--error-border)',
                display: 'flex',
                gap: 12,
                alignItems: 'center',
                color: 'var(--error)',
                fontWeight: 500,
              }}
            >
              <ExclamationCircleOutlined style={{ fontSize: 18 }} />
              <span>{error}</span>
            </div>
          </motion.div>
        )}

        {deviceInfo && (
          <motion.div variants={containerVariants} initial="hidden" animate="show">
            <Row gutter={[24, 24]}>
              <Col xs={24} lg={8}>
                <motion.div variants={itemVariants} style={{ height: '100%' }}>
                  <GlassCard intensity="low" className={styles.card}>
                    <div className={styles.cardHeader}>
                      <div className={styles.cardTitle}>计算平台</div>
                      <Tag
                        color={deviceInfo.platform === 'cuda' ? 'success' : 'processing'}
                        style={{ margin: 0, borderRadius: 'var(--radius-sm)' }}
                      >
                        {deviceInfo.platform.toUpperCase()}
                      </Tag>
                    </div>
                    
                    <div className={styles.platformCenter}>
                      <div className={styles.platformIconWrapper}>
                        {getPlatformIcon(deviceInfo.platform)}
                      </div>
                      <div className={styles.platformName}>
                        {getPlatformName(deviceInfo.platform)}
                      </div>
                      <div className={styles.deviceName}>{deviceInfo.device_name}</div>
                    </div>

                    <div className={styles.metricsRow}>
                      <div className={styles.metricItem}>
                        <span className={styles.metricLabel}>CUDA 可用</span>
                        <span className={styles.metricValue}>
                          {deviceInfo.cuda_available ? (
                            <span style={{ color: 'var(--success)' }}><CheckCircleOutlined /> 是</span>
                          ) : (
                            <span style={{ color: 'var(--text-tertiary)' }}>否</span>
                          )}
                        </span>
                      </div>
                      {deviceInfo.platform === 'mac' && (
                        <div className={styles.metricItem}>
                          <span className={styles.metricLabel}>MPS 可用</span>
                          <span className={styles.metricValue}>
                            {deviceInfo.mps_available ? (
                              <span style={{ color: 'var(--success)' }}><CheckCircleOutlined /> 是</span>
                            ) : (
                              <span style={{ color: 'var(--text-tertiary)' }}>否</span>
                            )}
                          </span>
                        </div>
                      )}
                    </div>
                  </GlassCard>
                </motion.div>
              </Col>

              <Col xs={24} lg={8}>
                <motion.div variants={itemVariants} style={{ height: '100%' }}>
                  <GlassCard intensity="low" className={styles.card}>
                    <div className={styles.cardHeader}>
                      <div className={styles.cardTitle}>GPU 显存 (VRAM)</div>
                      <ThunderboltOutlined style={{ color: 'var(--accent-primary)', fontSize: 16 }} />
                    </div>
                    <div className={styles.progressWrapper}>
                      <Progress
                        type="dashboard"
                        percent={
                          deviceInfo.vram_total
                            ? Math.round((deviceInfo.vram_used / deviceInfo.vram_total) * 100)
                            : 0
                        }
                        format={(percent) => (
                          <div className={styles.progressText}>
                            <span className={styles.progressPercent}>{percent}%</span>
                            <span className={styles.progressSub}>已使用</span>
                          </div>
                        )}
                        strokeColor={{ '0%': 'var(--accent-primary)', '100%': 'var(--warning)' }}
                        size={160}
                        strokeWidth={8}
                        gapDegree={90}
                      />
                      <div className={styles.metricsGrid}>
                        <div className={styles.metricBox}>
                          <div className={styles.metricBoxLabel}>已用显存</div>
                          <div className={styles.metricBoxValue}>
                            {(deviceInfo.vram_used || 0).toFixed(1)} <span className={styles.unit}>GB</span>
                          </div>
                        </div>
                        <div className={styles.metricBox}>
                          <div className={styles.metricBoxLabel}>可用显存</div>
                          <div className={styles.metricBoxValue} style={{ color: 'var(--success)' }}>
                            {(deviceInfo.vram_free || 0).toFixed(1)} <span className={styles.unit}>GB</span>
                          </div>
                        </div>
                        <div className={styles.metricBox} style={{ gridColumn: 'span 2' }}>
                          <div className={styles.metricBoxLabel}>总容量</div>
                          <div className={styles.metricBoxValue}>
                            {(deviceInfo.vram_total || 0).toFixed(1)} <span className={styles.unit}>GB</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </GlassCard>
                </motion.div>
              </Col>

              <Col xs={24} lg={8}>
                <motion.div variants={itemVariants} style={{ height: '100%' }}>
                  <GlassCard intensity="low" className={styles.card}>
                    <div className={styles.cardHeader}>
                      <div className={styles.cardTitle}>系统内存 (RAM)</div>
                      <DesktopOutlined style={{ color: 'var(--accent-secondary)', fontSize: 16 }} />
                    </div>
                    <div className={styles.progressWrapper}>
                      <Progress
                        type="dashboard"
                        percent={Math.round(
                          ((deviceInfo.memory_used || 0) / (deviceInfo.memory_total || 1)) * 100,
                        )}
                        format={(percent) => (
                          <div className={styles.progressText}>
                            <span className={styles.progressPercent}>{percent}%</span>
                            <span className={styles.progressSub}>已使用</span>
                          </div>
                        )}
                        strokeColor={{ '0%': 'var(--accent-secondary)', '100%': 'var(--warning)' }}
                        size={160}
                        strokeWidth={8}
                        gapDegree={90}
                      />
                      <div className={styles.metricsGrid}>
                        <div className={styles.metricBox}>
                          <div className={styles.metricBoxLabel}>已用内存</div>
                          <div className={styles.metricBoxValue}>
                            {(deviceInfo.memory_used || 0).toFixed(1)} <span className={styles.unit}>GB</span>
                          </div>
                        </div>
                        <div className={styles.metricBox}>
                          <div className={styles.metricBoxLabel}>可用内存</div>
                          <div className={styles.metricBoxValue} style={{ color: 'var(--success)' }}>
                            {(deviceInfo.memory_free || 0).toFixed(1)} <span className={styles.unit}>GB</span>
                          </div>
                        </div>
                        <div className={styles.metricBox} style={{ gridColumn: 'span 2' }}>
                          <div className={styles.metricBoxLabel}>总容量</div>
                          <div className={styles.metricBoxValue}>
                            {(deviceInfo.memory_total || 0).toFixed(1)} <span className={styles.unit}>GB</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </GlassCard>
                </motion.div>
              </Col>

              {/* 显存建议卡片 */}
              <Col xs={24}>
                <motion.div variants={itemVariants}>
                  <GlassCard intensity="low" className={styles.card}>
                    <div className={styles.cardHeader} style={{ borderBottom: 'none', paddingBottom: 0 }}>
                      <div className={styles.cardTitle}>微调配置建议</div>
                    </div>
                    
                    {(() => {
                      const suggestion = getVramSuggestion(deviceInfo.vram_free || 0);
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
                        <div
                          style={{
                            marginTop: '16px',
                            padding: '16px 20px',
                            background: 'var(--bg-elevated)',
                            borderRadius: 'var(--radius-md)',
                            borderLeft: `4px solid ${getColor()}`,
                            display: 'flex',
                            gap: 16,
                            alignItems: 'flex-start',
                          }}
                        >
                          <div style={{ fontSize: 24, color: getColor(), marginTop: 2 }}>
                            {getIcon()}
                          </div>
                          <div>
                            <div
                              style={{
                                fontWeight: 600,
                                color: 'var(--text-primary)',
                                marginBottom: 8,
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
                              }}
                            >
                              {suggestion.desc}
                            </div>
                          </div>
                        </div>
                      );
                    })()}
                  </GlassCard>
                </motion.div>
              </Col>
            </Row>
          </motion.div>
        )}
      </div>
    </AnimatedLayout>
  );
}
