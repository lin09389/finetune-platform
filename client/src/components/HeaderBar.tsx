import {
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Layout, Space, Tooltip } from 'antd';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { getDeviceInfo } from '../services/api';
import { useAppStore } from '../store/appStore';
import { useShallow } from 'zustand/react/shallow';
import styles from './HeaderBar.module.css';
import { NotificationPanel, useNotifications } from './NotificationPanel';
import ThemeToggle from './ThemeToggle';

const { Header } = Layout;

export default function HeaderBar() {
  const { backendStatus, setDeviceInfo } = useAppStore(useShallow(state => ({
    backendStatus: state.backendStatus,
    setDeviceInfo: state.setDeviceInfo
  })));
  const [loading, setLoading] = useState(false);
  const { notifications, addNotification, markAsRead, markAllAsRead, deleteNotification } =
    useNotifications();

  const fetchDeviceInfo = async () => {
    setLoading(true);
    try {
      const info = await getDeviceInfo();
      setDeviceInfo(info);
    } catch (error) {
      console.error('Failed to fetch device info:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (backendStatus === 'connected') {
      fetchDeviceInfo();
    }
  }, [backendStatus]);

  useEffect(() => {
    if (backendStatus === 'connected') {
      addNotification({
        type: 'success',
        title: '后端已连接',
        message: '成功连接到后端服务',
      });
    } else if (backendStatus === 'disconnected') {
      addNotification({
        type: 'error',
        title: '后端未连接',
        message: '无法连接到后端服务，请检查是否已启动',
      });
    }
  }, [backendStatus]);



  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
    >
      <Header className={styles.header}>
        <Space size="middle" align="center">
          {/* Status badge removed as requested */}
        </Space>

        <Space size="middle" align="center">
          <NotificationPanel
            notifications={notifications}
            onClear={markAllAsRead}
            onMarkAsRead={markAsRead}
            onDelete={deleteNotification}
          />

          <ThemeToggle />

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
  );
}
