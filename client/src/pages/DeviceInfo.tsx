import {
  AppleOutlined,
  DesktopOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Alert, Button, Col, Progress, Row, Spin, Tag } from 'antd';
import { useEffect, useState } from 'react';
import glassStyles from '../components/shared/GlassCard.module.css';
import { getDeviceInfo } from '../services/api';
import { useAppStore } from '../store/appStore';
import styles from './DeviceInfo.module.css';

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
        return <ThunderboltOutlined style={{ color: '#76b900' }} />;
      case 'mac':
        return <AppleOutlined style={{ color: '#555' }} />;
      default:
        return <QuestionCircleOutlined />;
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

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={`${glassStyles.glassCard} ${styles.headerCard}`}>
        <h1 className={styles.title}>
          <DesktopOutlined />
          设备信息
        </h1>
        <Button
          icon={<ReloadOutlined />}
          onClick={fetchInfo}
          loading={loading}
          style={{ borderRadius: 8 }}
        >
          刷新
        </Button>
      </div>

      {error && (
        <Alert
          message="错误"
          description={error}
          type="error"
          showIcon
          style={{ borderRadius: 12 }}
        />
      )}

      {deviceInfo && (
        <>
          <Row gutter={[24, 24]}>
            <Col xs={24} md={12}>
              <div className={`${glassStyles.glassCard} ${styles.card}`}>
                <div className={styles.cardTitle}>计算平台</div>
                <div className={styles.platformCenter}>
                  <div className={styles.platformIcon}>{getPlatformIcon(deviceInfo.platform)}</div>
                  <Tag
                    color={deviceInfo.platform === 'cuda' ? 'success' : 'purple'}
                    style={{ fontSize: 14, padding: '4px 16px', borderRadius: 6 }}
                  >
                    {getPlatformName(deviceInfo.platform)}
                  </Tag>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                    {deviceInfo.device_name}
                  </div>
                </div>
                <div className={styles.metricsRow} style={{ marginTop: 16 }}>
                  <div className={styles.metricItem}>
                    <span className={styles.metricLabel}>CUDA 可用</span>
                    <span className={styles.metricValue}>
                      {deviceInfo.cuda_available ? <Tag color="success">是</Tag> : <Tag>否</Tag>}
                    </span>
                  </div>
                  {deviceInfo.platform === 'mac' && (
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>MPS 可用</span>
                      <span className={styles.metricValue}>
                        {deviceInfo.mps_available ? <Tag color="success">是</Tag> : <Tag>否</Tag>}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </Col>

            <Col xs={24} md={12}>
              <div className={`${glassStyles.glassCard} ${styles.card}`}>
                <div className={styles.cardTitle}>显存 (VRAM)</div>
                <div className={styles.progressWrapper}>
                  <Progress
                    type="circle"
                    percent={
                      deviceInfo.vram_total
                        ? Math.round((deviceInfo.vram_used / deviceInfo.vram_total) * 100)
                        : 0
                    }
                    format={() =>
                      `${(deviceInfo.vram_used || 0).toFixed(1)}/${(deviceInfo.vram_total || 0).toFixed(1)}GB`
                    }
                    strokeColor={{ '0%': 'var(--accent-primary)', '100%': 'var(--success)' }}
                    size={140}
                  />
                  <div className={styles.metricsRow}>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>总容量</span>
                      <span className={styles.metricValue}>
                        {(deviceInfo.vram_total || 0).toFixed(1)} GB
                      </span>
                    </div>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>已使用</span>
                      <span className={styles.metricValue}>
                        {(deviceInfo.vram_used || 0).toFixed(1)} GB
                      </span>
                    </div>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>剩余可用</span>
                      <span className={styles.metricValue}>
                        {(deviceInfo.vram_free || 0).toFixed(1)} GB
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </Col>
          </Row>

          <Row gutter={[24, 24]}>
            <Col xs={24} md={12}>
              <div className={`${glassStyles.glassCard} ${styles.card}`}>
                <div className={styles.cardTitle}>系统内存 (RAM)</div>
                <div className={styles.progressWrapper}>
                  <Progress
                    type="circle"
                    percent={Math.round(
                      ((deviceInfo.memory_used || 0) / (deviceInfo.memory_total || 1)) * 100,
                    )}
                    format={() =>
                      `${(deviceInfo.memory_used || 0).toFixed(1)}/${(deviceInfo.memory_total || 0).toFixed(1)}GB`
                    }
                    strokeColor={{ '0%': 'var(--accent-primary)', '100%': 'var(--success)' }}
                    size={140}
                  />
                  <div className={styles.metricsRow}>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>总容量</span>
                      <span className={styles.metricValue}>
                        {(deviceInfo.memory_total || 0).toFixed(1)} GB
                      </span>
                    </div>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>已使用</span>
                      <span className={styles.metricValue}>
                        {(deviceInfo.memory_used || 0).toFixed(1)} GB
                      </span>
                    </div>
                    <div className={styles.metricItem}>
                      <span className={styles.metricLabel}>剩余可用</span>
                      <span className={styles.metricValue}>
                        {(deviceInfo.memory_free || 0).toFixed(1)} GB
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </Col>

            <Col xs={24} md={12}>
              <div className={`${glassStyles.glassCard} ${styles.alertCard}`}>
                <div className={styles.cardTitle}>显存建议</div>
                <div style={{ paddingTop: 8 }}>
                  {(deviceInfo.vram_free || 0) < 6 && (
                    <Alert
                      message="显存不足"
                      description="当前显存小于 6GB，建议使用 INT4 量化 + QLoRA。推荐：Qwen2.5-0.5B, Phi-3-mini"
                      type="warning"
                      showIcon
                      style={{ borderRadius: 10 }}
                    />
                  )}
                  {(deviceInfo.vram_free || 0) >= 6 && (deviceInfo.vram_free || 0) < 10 && (
                    <Alert
                      message="显存适中"
                      description="6-10GB 可用 INT4 微调 7B 模型，如 Qwen2.5-1.8B, Llama3-8B, ChatGLM3-6B"
                      type="success"
                      showIcon
                      style={{ borderRadius: 10 }}
                    />
                  )}
                  {(deviceInfo.vram_free || 0) >= 10 && (deviceInfo.vram_free || 0) < 16 && (
                    <Alert
                      message="显存充裕"
                      description="10-16GB 可微调 7B 模型（INT4/INT8），或用 QLoRA 微调 13B 模型"
                      type="success"
                      showIcon
                      style={{ borderRadius: 10 }}
                    />
                  )}
                  {deviceInfo.vram_free >= 16 && (
                    <Alert
                      message="显存充足"
                      description="16GB+ 可微调 13B 模型，或用 LoRA 微调 30B+ 模型"
                      type="success"
                      showIcon
                      style={{ borderRadius: 10 }}
                    />
                  )}
                </div>
              </div>
            </Col>
          </Row>
        </>
      )}
    </div>
  );
}
