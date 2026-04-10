import { useEffect } from 'react'
import { Row, Col, Progress, Table, Tag, Button, Empty } from 'antd'
import { motion } from 'framer-motion'
import {
  ThunderboltOutlined,
  FolderOutlined,
  DatabaseOutlined,
  ArrowRightOutlined,
  PlayCircleOutlined,
  CloudOutlined,
  MessageOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  RocketOutlined,
  SettingOutlined,
  PlusOutlined
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import { getDeviceInfo } from '../services/api'
import GlassCard from '../components/shared/GlassCard'
import AnimatedLayout from '../components/shared/AnimatedLayout'
import { CountUp } from '../components/shared/MotionWrapper'
import styles from './Dashboard.module.css'

interface QuickAction {
  title: string
  icon: React.ReactNode
  color: string
  onClick: () => void
  description: string
  stats?: string
}

interface StatCardProps {
  title: string
  value: number
  total?: number
  suffix?: string
  prefix?: React.ReactNode
  color: string
  icon: React.ReactNode
  progress?: number
  delay?: number
}

// 动画配置
const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08
    }
  }
}

const itemVariants = {
  hidden: { opacity: 0, y: 12, filter: 'blur(4px)' },
  show: { 
    opacity: 1, 
    y: 0,
    filter: 'blur(0px)',
    transition: {
      duration: 0.4,
      ease: [0.16, 1, 0.3, 1] as const
    }
  }
}

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
          <div style={{ 
            fontSize: 'var(--text-xs)', 
            color: 'var(--text-tertiary)', 
            marginBottom: 'var(--space-3)',
            fontWeight: 'var(--font-semibold)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em'
          }}>
            {title}
          </div>
          <div className={styles.statValue}>
            {prefix}
            <CountUp
              value={value}
              decimals={total ? 1 : 0}
            />
            {total !== undefined && (
              <span className={styles.statTotal}>
                / {total} {suffix}
              </span>
            )}
            {total === undefined && suffix && (
              <span className={styles.statTotal}>
                {suffix}
              </span>
            )}
          </div>
        </div>
        <div className={styles.statIcon} style={{ 
          background: color,
          color: '#fff',
          boxShadow: `0 4px 12px ${color}40`
        }}>
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
          <div style={{ 
            fontSize: 'var(--text-xs)', 
            color: 'var(--text-tertiary)', 
            marginTop: 'var(--space-2)',
            textAlign: 'right',
            fontWeight: 'var(--font-medium)'
          }}>
            {progress}% 已使用
          </div>
        </div>
      )}
    </GlassCard>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { backendStatus, deviceInfo, setDeviceInfo, models, datasets, trainingRecords } = useAppStore()

  const fetchDeviceInfo = async () => {
    if (backendStatus !== 'connected') return
    try {
      const info = await getDeviceInfo()
      setDeviceInfo(info)
    } catch (error) {
      console.error('Failed to fetch device info:', error)
    }
  }

  useEffect(() => {
    fetchDeviceInfo()
  }, [backendStatus])

  const recentTrainings = trainingRecords.slice(-5).reverse()

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
              padding: '2px 8px'
            }}
          >
            完成
          </Tag>
        )
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
              padding: '2px 8px'
            }}
          >
            失败
          </Tag>
        )
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
              padding: '2px 8px'
            }}
          >
            停止
          </Tag>
        )
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
              padding: '2px 8px'
            }}
          >
            训练中
          </Tag>
        )
    }
  }

  const trainingColumns = [
    {
      title: '模型',
      dataIndex: 'modelId',
      key: 'modelId',
      render: (id: string) => {
        const model = models.find(m => m.id === id)
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <FolderOutlined style={{ color: 'var(--accent-primary)', fontSize: '16px' }} />
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{model?.name || id}</span>
          </div>
        )
      }
    },
    {
      title: '数据集',
      dataIndex: 'datasetId',
      key: 'datasetId',
      render: (id: string) => {
        const dataset = datasets.find(d => d.id === id)
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <DatabaseOutlined style={{ color: 'var(--accent-secondary)', fontSize: '16px' }} />
            <span style={{ color: 'var(--text-secondary)' }}>{dataset?.name || id}</span>
          </div>
        )
      }
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
            padding: '2px 8px'
          }}
        >
          {method?.toUpperCase() || 'QLoRA'}
        </Tag>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => getStatusBadge(status)
    },
    {
      title: '时间',
      dataIndex: 'startTime',
      key: 'startTime',
      render: (date: string) => (
        <span style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)', fontWeight: 500 }}>
          {new Date(date).toLocaleString('zh-CN')}
        </span>
      )
    }
  ]

  const quickActions: QuickAction[] = [
    {
      title: '开始训练',
      icon: <RocketOutlined />,
      color: 'var(--accent-primary)',
      onClick: () => navigate('/training'),
      description: '创建并部署新的微调任务，支持 LoRA/QLoRA',
      stats: '快速启动'
    },
    {
      title: '模型管理',
      icon: <FolderOutlined />,
      color: 'var(--success)',
      onClick: () => navigate('/models'),
      description: '高效管理本地模型库，支持多格式导入与导出',
      stats: `${models.length} 个模型`
    },
    {
      title: '数据集管理',
      icon: <DatabaseOutlined />,
      color: 'var(--warning)',
      onClick: () => navigate('/datasets'),
      description: '上传并清洗您的训练数据集，支持 JSONL/CSV',
      stats: `${datasets.length} 个数据集`
    },
    {
      title: 'AI 对话',
      icon: <MessageOutlined />,
      color: 'var(--accent-secondary)',
      onClick: () => navigate('/chat'),
      description: '与您的模型进行实时对话，测试微调后的生成效果',
      stats: '立即体验'
    }
  ]

  return (
    <AnimatedLayout animationKey="dashboard">
      <div className={styles.dashboardContainer}>
        {/* 页面标题 */}
        <div className={styles.pageHeader}>
          <div className={styles.titleWrapper}>
            <div className={styles.titleIcon}>
              <ThunderboltOutlined />
            </div>
            <h1 className={styles.titleText}>仪表盘</h1>
          </div>
          <p className={styles.subtitle}>
            欢迎回来，这里是您的 AI 微调工作台概览。
          </p>
        </div>

        {backendStatus !== 'connected' ? (
          <GlassCard intensity="high" style={{ textAlign: 'center', padding: 'var(--space-12) var(--space-6)' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <div>
                  <p style={{ fontSize: 'var(--text-lg)', color: 'var(--text-secondary)', marginBottom: 'var(--space-6)' }}>
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
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            {/* 资源统计卡片 */}
            <Row gutter={[24, 24]} style={{ marginBottom: 'var(--space-8)' }}>
              <Col xs={24} sm={12} lg={6}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="GPU 显存"
                    value={deviceInfo?.vram_free || 0}
                    total={deviceInfo?.vram_total || 0}
                    suffix="GB"
                    color="var(--accent-primary)"
                    icon={<ThunderboltOutlined />}
                    progress={Math.round(((deviceInfo?.vram_total || 1) - (deviceInfo?.vram_free || 0)) / (deviceInfo?.vram_total || 1) * 100)}
                  />
                </motion.div>
              </Col>

              <Col xs={24} sm={12} lg={6}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="系统内存"
                    value={deviceInfo?.memory_free || 0}
                    total={deviceInfo?.memory_total || 0}
                    suffix="GB"
                    color="var(--accent-secondary)"
                    icon={<DatabaseOutlined />}
                    progress={Math.round(((deviceInfo?.memory_total || 1) - (deviceInfo?.memory_free || 0)) / (deviceInfo?.memory_total || 1) * 100)}
                  />
                </motion.div>
              </Col>

              <Col xs={24} sm={12} lg={6}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="模型数量"
                    value={models.length}
                    color="var(--success)"
                    icon={<FolderOutlined />}
                  />
                </motion.div>
              </Col>

              <Col xs={24} sm={12} lg={6}>
                <motion.div variants={itemVariants}>
                  <StatCard
                    title="数据集数量"
                    value={datasets.length}
                    color="var(--warning)"
                    icon={<CloudOutlined />}
                  />
                </motion.div>
              </Col>
            </Row>

            {/* 快捷操作 */}
            <div style={{ marginBottom: 'var(--space-8)' }}>
              <h3 className={styles.sectionTitle}>
                <PlayCircleOutlined style={{ color: 'var(--accent-primary)' }} />
                快捷操作
              </h3>
              <Row gutter={[24, 24]}>
                {quickActions.map((action, index) => (
                  <Col xs={24} sm={12} lg={6} key={index}>
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
                        <div className={styles.quickActionIcon} style={{ 
                          background: `${action.color}18`,
                          color: action.color,
                          border: `1px solid ${action.color}30`
                        }}>
                          {action.icon}
                        </div>
                        <div>
                          <div className={styles.quickActionTitle}>
                            {action.title}
                          </div>
                          <div className={styles.quickActionDesc}>
                            {action.description}
                          </div>
                          {action.stats && (
                            <Tag 
                              style={{ 
                                background: 'rgba(0, 0, 0, 0.05)',
                                color: 'var(--text-secondary)',
                                border: '1px solid var(--border-color)',
                                borderRadius: 'var(--radius-sm)',
                                fontSize: 'var(--text-xs)',
                                fontWeight: 600,
                                padding: '2px 8px'
                              }}
                            >
                              {action.stats}
                            </Tag>
                          )}
                        </div>
                      </GlassCard>
                    </motion.div>
                  </Col>
                ))}
              </Row>
            </div>

            {/* 最近训练记录 */}
            <motion.div variants={itemVariants}>
              <GlassCard
                className={styles.historyCard}
                intensity="medium"
                noHover
              >
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
                          <p style={{ color: 'var(--text-tertiary)', marginBottom: 'var(--space-4)' }}>暂无训练记录</p>
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
  )
}
