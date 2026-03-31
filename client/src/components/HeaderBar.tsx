import { Layout, Space, Tag, Button, Tooltip, Select, Badge, Avatar, Divider } from 'antd'
import { motion } from 'framer-motion'
import { 
  ReloadOutlined, 
  MoonOutlined, 
  SunOutlined, 
  LaptopOutlined, 
  UserOutlined, 
  ThunderboltOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { useEffect, useState } from 'react'
import { getDeviceInfo } from '../services/api'
import { NotificationPanel, useNotifications } from './NotificationPanel'
import styles from './HeaderBar.module.css'

const { Header } = Layout

export default function HeaderBar() {
  const { backendStatus, deviceInfo, setDeviceInfo, themeMode, setThemeMode } = useAppStore()
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
            text={<span style={{ color: 'var(--success)', fontWeight: 600, fontSize: 11 }}>ONLINE</span>}
          />
        )
      case 'disconnected':
        return (
          <Badge
            status="error"
            text={<span style={{ color: 'var(--error)', fontWeight: 600, fontSize: 11 }}>OFFLINE</span>}
          />
        )
      default:
        return (
          <Badge
            status="default"
            text={<span style={{ color: 'var(--text-tertiary)', fontWeight: 600, fontSize: 11 }}>CHECKING</span>}
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
        <Tag color="blue" style={{ borderRadius: 'var(--radius-sm)', fontWeight: 700, fontSize: 10, margin: 0 }}>
          <ThunderboltOutlined style={{ marginRight: 4 }} />
          CUDA
        </Tag>
      )
    } else if (deviceInfo.platform === 'mac') {
      return (
        <Tag color="geekblue" style={{ borderRadius: 'var(--radius-sm)', fontWeight: 700, fontSize: 10, margin: 0 }}>
          MPS
        </Tag>
      )
    }
    return (
      <Tag color="default" style={{ borderRadius: 'var(--radius-sm)', fontWeight: 700, fontSize: 10, margin: 0 }}>
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
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
    >
      <Header className={styles.header}>
        {/* 左侧 - 状态信息 */}
        <Space size="middle" align="center">
          <motion.div
            className={styles.statusCard}
            whileHover={{ scale: 1.02 }}
          >
            {getStatusBadge()}
            <Divider type="vertical" style={{ margin: 0, height: 16, borderColor: 'var(--glass-border)' }} />
            {getPlatformIcon()}
          </motion.div>

          {/* 资源统计 */}
          {deviceInfo?.vram_free !== undefined && (
            <div className={styles.resourceStats}>
              <div className={styles.statItem}>
                <div className={styles.statLabel}>VRAM</div>
                <div className={styles.statValue}>
                  {(deviceInfo.vram_free ?? 0).toFixed(1)}
                  <span className={styles.statSuffix}>GB</span>
                </div>
                <div className={styles.progressBar}>
                  <motion.div
                    className={styles.progressFill}
                    initial={{ width: 0 }}
                    animate={{ width: `${((deviceInfo.vram_free ?? 0) / (deviceInfo.vram_total ?? 1)) * 100}%` }}
                    style={{ background: (deviceInfo.vram_free ?? 0) / (deviceInfo.vram_total ?? 1) > 0.3 ? 'var(--success)' : 'var(--error)' }}
                  />
                </div>
              </div>
              <div className={styles.statItem}>
                <div className={styles.statLabel}>RAM</div>
                <div className={styles.statValue}>
                  {(deviceInfo.memory_free ?? 0).toFixed(1)}
                  <span className={styles.statSuffix}>GB</span>
                </div>
                <div className={styles.progressBar}>
                  <motion.div
                    className={styles.progressFill}
                    initial={{ width: 0 }}
                    animate={{ width: `${((deviceInfo.memory_free ?? 0) / (deviceInfo.memory_total ?? 1)) * 100}%` }}
                    style={{ background: (deviceInfo.memory_free ?? 0) / (deviceInfo.memory_total ?? 1) > 0.3 ? 'var(--info)' : 'var(--error)' }}
                  />
                </div>
              </div>
            </div>
          )}
        </Space>

        {/* 右侧 - 操作按钮 */}
        <Space size="middle" align="center">
          {/* 时间显示 */}
          <motion.div
            className={styles.timeDisplay}
            whileHover={{ scale: 1.02 }}
          >
            <ClockCircleOutlined style={{ marginRight: 8, fontSize: 12 }} />
            {currentTime.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </motion.div>

          <Divider type="vertical" style={{ margin: 0, height: 20, borderColor: 'var(--glass-border)' }} />

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
            style={{ width: 110 }}
            suffixIcon={getThemeIcon()}
            options={themeItems}
            variant="borderless"
            popupClassName={styles.themePopup}
          />

          {/* 刷新按钮 */}
          <Tooltip title="刷新状态">
            <Button
              className={styles.actionBtn}
              icon={<ReloadOutlined spin={loading} />}
              onClick={fetchDeviceInfo}
              loading={loading}
              size="small"
              style={{ width: 32, height: 32 }}
            />
          </Tooltip>

          {/* 用户头像 */}
          <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}>
            <Avatar
              icon={<UserOutlined />}
              style={{
                background: 'var(--text-primary)',
                color: 'var(--text-inverse)',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-sm)',
              }}
            />
          </motion.div>
        </Space>
      </Header>
    </motion.div>
  )
}
