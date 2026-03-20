import { useEffect, useState } from 'react'
import { Card, Row, Col, Progress, Table, Tag, Space, Button, Empty } from 'antd'
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
      staggerChildren: 0.05
    }
  }
}

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  show: { 
    opacity: 1, 
    y: 0,
    transition: {
      duration: 0.3,
      ease: [0.16, 1, 0.3, 1] as const
    }
  }
}

const cardHoverVariants = {
  hover: { 
    y: -2,
    transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] as const }
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
  delay = 0
}) => {
  return (
    <motion.div
      variants={itemVariants}
      whileHover="hover"
      initial="hidden"
      animate="show"
      transition={{ delay: delay * 0.05 }}
    >
      <motion.div variants={cardHoverVariants}>
        <Card
          className="stat-card"
          style={{
            borderRadius: '8px',
            border: '1px solid var(--border-color)',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.02)',
            overflow: 'hidden',
          }}
          styles={{ body: { padding: '20px' } }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
              <div style={{ 
                fontSize: 'var(--text-xs)', 
                color: 'var(--text-secondary)', 
                marginBottom: 'var(--space-2)',
                fontWeight: 'var(--font-medium)',
                textTransform: 'uppercase',
                letterSpacing: 'var(--tracking-wide)'
              }}>
                {title}
              </div>
              <div style={{ 
                fontSize: 'var(--text-3xl)', 
                fontWeight: 'var(--font-semibold)', 
                color: 'var(--text-primary)',
                display: 'flex',
                alignItems: 'baseline',
                gap: 'var(--space-1)',
              }}>
                {prefix}
                {value.toFixed(total ? 1 : 0)}
                {total !== undefined && (
                  <span style={{ 
                    fontSize: 'var(--text-sm)', 
                    fontWeight: 'var(--font-normal)', 
                    color: 'var(--text-tertiary)' 
                  }}>
                    / {total} {suffix}
                  </span>
                )}
                {total === undefined && suffix && (
                  <span style={{ 
                    fontSize: 'var(--text-sm)', 
                    fontWeight: 'var(--font-normal)', 
                    color: 'var(--text-tertiary)' 
                  }}>
                    {suffix}
                  </span>
                )}
              </div>
            </div>
            <div style={{
              width: 44,
              height: 44,
              borderRadius: 'var(--radius-lg)',
              background: color,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 'var(--text-xl)',
              color: 'var(--text-inverse)',
            }}>
              {icon}
            </div>
          </div>
          
          {progress !== undefined && (
            <div style={{ marginTop: 16 }}>
              <Progress
                percent={progress}
                strokeColor={color}
                trailColor="var(--border-color)"
                size={{ height: 4 }}
                showInfo={false}
                style={{ margin: 0 }}
              />
              <div style={{ 
                fontSize: '12px', 
                color: 'var(--text-tertiary)', 
                marginTop: 6,
                textAlign: 'right'
              }}>
                {progress}% 已使用
              </div>
            </div>
          )}
        </Card>
      </motion.div>
    </motion.div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { backendStatus, deviceInfo, setDeviceInfo, models, datasets, trainingRecords } = useAppStore()
  const [, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

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
              borderRadius: '4px', 
              fontWeight: 500,
              background: 'var(--success-light)',
              borderColor: 'var(--success)',
              color: 'var(--success)'
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
              borderRadius: '4px', 
              fontWeight: 500,
              background: 'var(--error-light)',
              borderColor: 'var(--error)',
              color: 'var(--error)'
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
              borderRadius: '4px', 
              fontWeight: 500,
              background: 'var(--warning-light)',
              borderColor: 'var(--warning)',
              color: 'var(--warning)'
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
              borderRadius: '4px', 
              fontWeight: 500,
              background: 'var(--info-light)',
              borderColor: 'var(--info)',
              color: 'var(--info)'
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FolderOutlined style={{ color: 'var(--accent-primary)' }} />
            <span style={{ fontWeight: 500 }}>{model?.name || id}</span>
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <DatabaseOutlined style={{ color: 'var(--accent-secondary)' }} />
            <span>{dataset?.name || id}</span>
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
            borderRadius: '4px', 
            fontWeight: 500,
            background: method === 'qlora' ? 'var(--success-light)' : 'var(--info-light)',
            borderColor: method === 'qlora' ? 'var(--success)' : 'var(--info)',
            color: method === 'qlora' ? 'var(--success)' : 'var(--info)'
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
        <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
          {new Date(date).toLocaleString('zh-CN')}
        </span>
      )
    }
  ]

  const quickActions: QuickAction[] = [
    {
      title: '开始训练',
      icon: <RocketOutlined />,
      color: '#2d2d2d',
      onClick: () => navigate('/training'),
      description: '创建新的微调任务',
      stats: '快速启动'
    },
    {
      title: '模型管理',
      icon: <FolderOutlined />,
      color: '#5b8a72',
      onClick: () => navigate('/models'),
      description: '下载或管理模型',
      stats: `${models.length} 个模型`
    },
    {
      title: '数据集管理',
      icon: <DatabaseOutlined />,
      color: '#d4a373',
      onClick: () => navigate('/datasets'),
      description: '上传训练数据',
      stats: `${datasets.length} 个数据集`
    },
    {
      title: 'AI 对话',
      icon: <MessageOutlined />,
      color: '#6b7280',
      onClick: () => navigate('/chat'),
      description: '测试模型效果',
      stats: '立即体验'
    }
  ]

  return (
    <motion.div 
      style={{ padding: '0 24px 24px' }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* 页面标题 */}
      <motion.div 
        className="page-header"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        style={{ marginBottom: 24 }}
      >
        <h1 style={{ 
          fontSize: '24px', 
          fontWeight: 600, 
          margin: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          color: 'var(--text-primary)'
        }}>
          <span style={{
            width: 36,
            height: 36,
            borderRadius: '8px',
            background: '#2d2d2d',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '18px',
            color: '#fff',
          }}>
            <ThunderboltOutlined />
          </span>
          仪表盘
        </h1>
        <p style={{ 
          margin: '8px 0 0 48px', 
          color: 'var(--text-secondary)',
          fontSize: '14px'
        }}>
          欢迎回来，这里是您的 AI 微调工作台概览
        </p>
      </motion.div>

      {backendStatus !== 'connected' ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
        >
          <Card
            style={{
              borderRadius: '8px',
              textAlign: 'center',
              padding: '60px 20px',
              border: '1px solid var(--border-color)',
            }}
          >
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <div>
                  <p style={{ fontSize: '16px', color: 'var(--text-secondary)', marginBottom: 16 }}>
                    后端服务未连接，请先启动应用
                  </p>
                  <Button 
                    type="primary" 
                    icon={<SettingOutlined />}
                    onClick={() => navigate('/device')}
                  >
                    查看设备状态
                  </Button>
                </div>
              }
            />
          </Card>
        </motion.div>
      ) : (
        <>
          {/* 资源统计卡片 */}
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
              <Col xs={24} sm={12} lg={6}>
                <StatCard
                  title="GPU 显存"
                  value={deviceInfo?.vram_free || 0}
                  total={deviceInfo?.vram_total || 0}
                  suffix="GB"
                  color="#2d2d2d"
                  icon={<ThunderboltOutlined />}
                  progress={Math.round(((deviceInfo?.vram_total || 1) - (deviceInfo?.vram_free || 0)) / (deviceInfo?.vram_total || 1) * 100)}
                  delay={0}
                />
              </Col>

              <Col xs={24} sm={12} lg={6}>
                <StatCard
                  title="系统内存"
                  value={deviceInfo?.memory_free || 0}
                  total={deviceInfo?.memory_total || 0}
                  suffix="GB"
                  color="#5b8a72"
                  icon={<DatabaseOutlined />}
                  progress={Math.round(((deviceInfo?.memory_total || 1) - (deviceInfo?.memory_free || 0)) / (deviceInfo?.memory_total || 1) * 100)}
                  delay={1}
                />
              </Col>

              <Col xs={24} sm={12} lg={6}>
                <StatCard
                  title="模型数量"
                  value={models.length}
                  color="#d4a373"
                  icon={<FolderOutlined />}
                  delay={2}
                />
              </Col>

              <Col xs={24} sm={12} lg={6}>
                <StatCard
                  title="数据集数量"
                  value={datasets.length}
                  color="#6b7280"
                  icon={<CloudOutlined />}
                  delay={3}
                />
              </Col>
            </Row>
          </motion.div>

          {/* 快捷操作 */}
          <motion.div 
            style={{ marginBottom: 24 }}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <h3 style={{ 
              fontSize: '16px', 
              fontWeight: 600, 
              marginBottom: 16,
              color: 'var(--text-primary)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}>
              <PlayCircleOutlined style={{ color: 'var(--accent-primary)' }} />
              快捷操作
            </h3>
            <Row gutter={[16, 16]}>
              {quickActions.map((action, index) => (
                <Col xs={24} sm={12} lg={6} key={index}>
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ 
                      duration: 0.3, 
                      delay: 0.3 + index * 0.05,
                      ease: [0.16, 1, 0.3, 1]
                    }}
                    whileHover={{ y: -2 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <Card
                      className="quick-action-card"
                      onClick={action.onClick}
                      style={{
                        borderRadius: '8px',
                        border: '1px solid var(--border-color)',
                        cursor: 'pointer',
                        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.02)',
                        overflow: 'hidden',
                        position: 'relative',
                      }}
                      styles={{ body: { padding: '24px' } }}
                    >
                      {/* 背景装饰 */}
                      <div style={{
                        position: 'absolute',
                        top: -20,
                        right: -20,
                        width: 80,
                        height: 80,
                        borderRadius: '50%',
                        background: action.color,
                        opacity: 0.05,
                      }} />
                      
                      <Space direction="vertical" size="middle" style={{ width: '100%', position: 'relative', zIndex: 1 }}>
                        <div style={{
                          width: 48,
                          height: 48,
                          borderRadius: '8px',
                          background: action.color,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '24px',
                          color: '#fff',
                        }}>
                          {action.icon}
                        </div>
                        <div>
                          <div style={{ 
                            fontWeight: 600, 
                            fontSize: '15px',
                            color: 'var(--text-primary)',
                            marginBottom: 4,
                          }}>
                            {action.title}
                          </div>
                          <div style={{ 
                            color: 'var(--text-secondary)', 
                            fontSize: '13px',
                            marginBottom: 8,
                          }}>
                            {action.description}
                          </div>
                          {action.stats && (
                            <Tag 
                              style={{ 
                                background: 'var(--bg-elevated)',
                                color: 'var(--text-secondary)',
                                border: '1px solid var(--border-color)',
                                borderRadius: '4px',
                                fontSize: '12px',
                                fontWeight: 500,
                              }}
                            >
                              {action.stats}
                            </Tag>
                          )}
                        </div>
                      </Space>
                    </Card>
                  </motion.div>
                </Col>
              ))}
            </Row>
          </motion.div>

          {/* 最近训练记录 */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
          >
            <Card
              className="training-history-card"
              style={{
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                boxShadow: '0 1px 3px rgba(0, 0, 0, 0.02)',
              }}
              title={
                <div style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  padding: '4px 0',
                }}>
                  <span style={{ 
                    fontSize: '16px', 
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}>
                    <ClockCircleOutlined style={{ color: 'var(--accent-primary)' }} />
                    最近训练
                  </span>
                  <Button 
                    type="link" 
                    icon={<ArrowRightOutlined />}
                    onClick={() => navigate('/history')}
                    style={{ fontWeight: 500 }}
                  >
                    查看全部
                  </Button>
                </div>
              }
            >
              {recentTrainings.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <div>
                      <p style={{ color: 'var(--text-secondary)' }}>暂无训练记录</p>
                      <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={() => navigate('/training')}
                        style={{ marginTop: 8 }}
                      >
                        开始训练
                      </Button>
                    </div>
                  }
                  style={{ padding: '40px 0' }}
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
            </Card>
          </motion.div>
        </>
      )}

      <style>{`
        .stat-card {
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        .stat-card:hover {
          border-color: var(--border-hover);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
        }
        
        .quick-action-card {
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        .quick-action-card:hover {
          border-color: var(--border-hover);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
        }
        
        .training-history-card .ant-card-head {
          border-bottom: 1px solid var(--border-color);
        }
        
        .training-history-card .ant-table {
          background: transparent;
        }
        
        .training-history-card .ant-table-thead > tr > th {
          background: var(--bg-elevated);
          border-bottom: 1px solid var(--border-color);
        }
        
        .training-history-card .ant-table-tbody > tr:hover > td {
          background: var(--bg-hover);
        }
      `}</style>
    </motion.div>
  )
}
