import { Layout, Space, Tag, Button, Tooltip, Row, Col, Select, Badge, Avatar, Divider } from 'antd'
import { motion } from 'framer-motion'
import { ReloadOutlined, MoonOutlined, SunOutlined, LaptopOutlined, UserOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { useEffect, useState } from 'react'
import { getDeviceInfo } from '../services/api'
import { NotificationPanel, useNotifications } from './NotificationPanel'

const { Header } = Layout

export default function HeaderBar() {
  const { backendStatus, deviceInfo, setDeviceInfo, themeMode, setThemeMode, sidebarCollapsed } = useAppStore()
  const [loading, setLoading] = useState(false)
  const [currentTime, setCurrentTime] = useState(new Date())
  const {
    notifications,
    addNotification,
    markAsRead,
    markAllAsRead,
    deleteNotification
  } = useNotifications()

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const fetchDeviceInfo = async () => {
    setLoading(true)
    try {
      const info = await getDeviceInfo()
      setDeviceInfo(info)
    } catch (error) {
      console.error('Failed to fetch device info:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (backendStatus === 'connected') {
      fetchDeviceInfo()
    }
  }, [backendStatus])

  useEffect(() => {
    if (backendStatus === 'connected') {
      addNotification({
        type: 'success',
        title: '后端已连接',
        message: '成功连接到后端服务'
      })
    } else if (backendStatus === 'disconnected') {
      addNotification({
        type: 'error',
        title: '后端未连接',
        message: '无法连接到后端服务，请检查是否已启动'
      })
    }
  }, [backendStatus])

  const getStatusBadge = () => {
    switch (backendStatus) {
      case 'connected':
        return (
          <Badge
            status="success"
            text={<span style={{ color: 'var(--success)', fontWeight: 500 }}>已连接</span>}
          />
        )
      case 'disconnected':
        return (
          <Badge
            status="error"
            text={<span style={{ color: 'var(--error)', fontWeight: 500 }}>未连接</span>}
          />
        )
      default:
        return (
          <Badge
            status="default"
            text={<span style={{ color: 'var(--text-tertiary)', fontWeight: 500 }}>检测中</span>}
          />
        )
    }
  }

  const getThemeIcon = () => {
    switch (themeMode) {
      case 'dark':
        return <MoonOutlined />
      case 'light':
        return <SunOutlined />
      default:
        return <LaptopOutlined />
    }
  }

  const getPlatformIcon = () => {
    if (!deviceInfo) return null
    if (deviceInfo.platform === 'cuda') {
      return (
        <Tag
          style={{
            borderRadius: '4px',
            fontWeight: 500,
            background: 'var(--info-light)',
            borderColor: 'var(--info)',
            color: 'var(--info)'
          }}
        >
          <ThunderboltOutlined style={{ marginRight: 4 }} />
          NVIDIA GPU
        </Tag>
      )
    } else if (deviceInfo.platform === 'mac') {
      return (
        <Tag
          style={{
            borderRadius: '4px',
            fontWeight: 500,
            background: 'var(--bg-elevated)',
            borderColor: 'var(--border-color)',
            color: 'var(--text-secondary)'
          }}
        >
          Apple Silicon
        </Tag>
      )
    }
    return (
      <Tag
        style={{
          borderRadius: '4px',
          fontWeight: 500,
          background: 'var(--bg-elevated)',
          borderColor: 'var(--border-color)',
          color: 'var(--text-secondary)'
        }}
      >
        CPU
      </Tag>
    )
  }

  const themeItems = [
    { key: 'light', label: '浅色模式', icon: <SunOutlined /> },
    { key: 'dark', label: '深色模式', icon: <MoonOutlined /> },
    { key: 'system', label: '跟随系统', icon: <LaptopOutlined /> }
  ]

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
    >
      <Header
        style={{
          padding: '0 24px',
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: 64,
          position: 'sticky',
          top: 0,
          zIndex: 99,
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
        }}
      >
        {/* 左侧 - 状态信息 */}
        <Space size="large" align="center">
          <motion.div
            className="status-card"
            whileHover={{ borderColor: 'var(--border-hover)' }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '8px 16px',
              background: 'var(--bg-elevated)',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              transition: 'all 0.2s ease',
            }}
          >
            {getStatusBadge()}
            <Divider type="vertical" style={{ margin: 0, height: 16, borderColor: 'var(--border-color)' }} />
            {getPlatformIcon()}
          </motion.div>

          {/* 资源统计 - 仅在侧边栏展开时显示 */}
          {deviceInfo?.vram_free !== undefined && !sidebarCollapsed && (
            <Row
              gutter={24}
              className="resource-stats"
            >
              <Col>
                <div style={{ textAlign: 'center' }}>
                  <div style={{
                    fontSize: '11px',
                    color: 'var(--text-tertiary)',
                    marginBottom: 2,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px'
                  }}>
                    显存可用
                  </div>
                  <div style={{
                    fontSize: '16px',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    display: 'flex',
                    alignItems: 'baseline',
                    gap: 4,
                  }}>
                    {(deviceInfo.vram_free ?? 0).toFixed(1)}
                    <span style={{ fontSize: '11px', fontWeight: 400, color: 'var(--text-secondary)' }}>GB</span>
                  </div>
                  <div style={{
                    width: 50,
                    height: 3,
                    background: 'var(--border-color)',
                    borderRadius: '2px',
                    marginTop: 4,
                    overflow: 'hidden',
                  }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${((deviceInfo.vram_free ?? 0) / (deviceInfo.vram_total ?? 1)) * 100}%` }}
                      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                      style={{
                        height: '100%',
                        background: (deviceInfo.vram_free ?? 0) / (deviceInfo.vram_total ?? 1) > 0.3 ? 'var(--success)' : 'var(--warning)',
                        borderRadius: '2px',
                      }}
                    />
                  </div>
                </div>
              </Col>
              <Col>
                <div style={{ textAlign: 'center' }}>
                  <div style={{
                    fontSize: '11px',
                    color: 'var(--text-tertiary)',
                    marginBottom: 2,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px'
                  }}>
                    内存可用
                  </div>
                  <div style={{
                    fontSize: '16px',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    display: 'flex',
                    alignItems: 'baseline',
                    gap: 4,
                  }}>
                    {(deviceInfo.memory_free ?? 0).toFixed(1)}
                    <span style={{ fontSize: '11px', fontWeight: 400, color: 'var(--text-secondary)' }}>GB</span>
                  </div>
                  <div style={{
                    width: 50,
                    height: 3,
                    background: 'var(--border-color)',
                    borderRadius: '2px',
                    marginTop: 4,
                    overflow: 'hidden',
                  }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${((deviceInfo.memory_free ?? 0) / (deviceInfo.memory_total ?? 1)) * 100}%` }}
                      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                      style={{
                        height: '100%',
                        background: (deviceInfo.memory_free ?? 0) / (deviceInfo.memory_total ?? 1) > 0.3 ? 'var(--info)' : 'var(--warning)',
                        borderRadius: '2px',
                      }}
                    />
                  </div>
                </div>
              </Col>
            </Row>
          )}
        </Space>

        {/* 右侧 - 操作按钮 */}
        <Space size="middle" align="center">
          {/* 时间显示 */}
          <motion.div
            className="time-display"
            whileHover={{ borderColor: 'var(--border-hover)' }}
            style={{
              padding: '6px 12px',
              background: 'var(--bg-elevated)',
              borderRadius: '6px',
              fontSize: '13px',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)',
              fontWeight: 500,
              letterSpacing: '0.5px',
              border: '1px solid var(--border-color)',
              transition: 'all 0.2s ease',
            }}
          >
            {currentTime.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </motion.div>

          {/* 通知面板 */}
          <NotificationPanel
            notifications={notifications}
            onClear={markAllAsRead}
            onMarkAsRead={markAsRead}
            onDelete={deleteNotification}
          />

          {/* 主题切换 */}
          <Select
            value={themeMode}
            onChange={(value) => setThemeMode(value)}
            style={{ width: 120 }}
            suffixIcon={getThemeIcon()}
            options={themeItems}
            variant="borderless"
            styles={{
              popup: {
                root: {
                  borderRadius: '8px',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08)',
                }
              }
            }}
          />

          {/* 刷新按钮 */}
          <Tooltip title="刷新设备信息">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Button
                icon={<ReloadOutlined spin={loading} />}
                onClick={fetchDeviceInfo}
                loading={loading}
                style={{
                  borderRadius: '6px',
                  width: 32,
                  height: 32,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderColor: 'var(--border-color)',
                }}
              />
            </motion.div>
          </Tooltip>

          {/* 用户头像 */}
          <Tooltip title="用户设置">
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <Avatar
                icon={<UserOutlined />}
                style={{
                  background: '#2d2d2d',
                  cursor: 'pointer',
                }}
              />
            </motion.div>
          </Tooltip>
        </Space>

        <style>{`
          .status-card:hover {
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
          }

          @media (max-width: 992px) {
            .resource-stats {
              display: none !important;
            }
          }

          @media (max-width: 768px) {
            .ant-layout-header {
              padding: 0 16px !important;
            }

            .time-display {
              display: none;
            }
          }
        `}</style>
      </Header>
    </motion.div>
  )
}
