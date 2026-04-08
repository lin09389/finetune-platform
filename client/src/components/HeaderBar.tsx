import { Layout, Space, Tag, Button, Tooltip, Select, Badge, Avatar } from 'antd'
import { motion } from 'framer-motion'
import {
  ReloadOutlined,
  MoonOutlined,
  SunOutlined,
  LaptopOutlined,
  UserOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { useEffect, useMemo, useState } from 'react'
import { getDeviceInfo } from '../services/api'
import { NotificationPanel, useNotifications } from './NotificationPanel'
import styles from './HeaderBar.module.css'

const { Header } = Layout

export default function HeaderBar() {
  const { backendStatus, deviceInfo, setDeviceInfo, themeMode, setThemeMode } = useAppStore()
  const [loading, setLoading] = useState(false)
  const { notifications, addNotification, markAsRead, markAllAsRead, deleteNotification } = useNotifications()

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
        message: '成功连接到后端服务',
      })
    } else if (backendStatus === 'disconnected') {
      addNotification({
        type: 'error',
        title: '后端未连接',
        message: '无法连接到后端服务，请检查是否已启动',
      })
    }
  }, [backendStatus])

  const getStatusBadge = () => {
    switch (backendStatus) {
      case 'connected':
        return <Badge status="success" text={<span style={{ color: 'var(--success)', fontWeight: 600, fontSize: 11 }}>ONLINE</span>} />
      case 'disconnected':
        return <Badge status="error" text={<span style={{ color: 'var(--error)', fontWeight: 600, fontSize: 11 }}>OFFLINE</span>} />
      default:
        return <Badge status="default" text={<span style={{ color: 'var(--text-tertiary)', fontWeight: 600, fontSize: 11 }}>CHECKING</span>} />
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

  const getPlatformTag = () => {
    if (!deviceInfo) return null

    if (deviceInfo.platform === 'cuda') {
      return (
        <Tag color="blue" style={{ borderRadius: 'var(--radius-sm)', fontWeight: 700, fontSize: 10, margin: 0 }}>
          <ThunderboltOutlined style={{ marginRight: 4 }} />
          CUDA
        </Tag>
      )
    }

    if (deviceInfo.platform === 'mac') {
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

  const resourceSummary = useMemo(() => {
    if (!deviceInfo) return '设备信息加载中'
    return `VRAM ${(deviceInfo.vram_free ?? 0).toFixed(1)}GB / ${(deviceInfo.vram_total ?? 0).toFixed(1)}GB，RAM ${(deviceInfo.memory_free ?? 0).toFixed(1)}GB / ${(deviceInfo.memory_total ?? 0).toFixed(1)}GB`
  }, [deviceInfo])

  const themeItems = [
    { key: 'light', label: '浅色模式', icon: <SunOutlined /> },
    { key: 'dark', label: '深色模式', icon: <MoonOutlined /> },
    { key: 'system', label: '跟随系统', icon: <LaptopOutlined /> },
  ]

  return (
    <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}>
      <Header className={styles.header}>
        <Space size="middle" align="center">
          <Tooltip title={resourceSummary}>
            <motion.div className={styles.statusCard} whileHover={{ scale: 1.02 }}>
              {getStatusBadge()}
              {getPlatformTag()}
            </motion.div>
          </Tooltip>
        </Space>

        <Space size="middle" align="center">
          <NotificationPanel
            notifications={notifications}
            onClear={markAllAsRead}
            onMarkAsRead={markAsRead}
            onDelete={deleteNotification}
          />

          <Select
            value={themeMode}
            onChange={(value) => setThemeMode(value)}
            style={{ width: 104 }}
            suffixIcon={getThemeIcon()}
            options={themeItems}
            variant="borderless"
            classNames={{ popup: { root: styles.themePopup } }}
          />

          <Tooltip title="刷新设备状态">
            <Button
              className={styles.actionBtn}
              icon={<ReloadOutlined spin={loading} />}
              onClick={fetchDeviceInfo}
              loading={loading}
              size="small"
              style={{ width: 32, height: 32 }}
            />
          </Tooltip>

          <motion.div whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.94 }}>
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
