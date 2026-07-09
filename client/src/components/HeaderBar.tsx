import {
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Layout, Space, Tooltip } from 'antd';
import { motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { getDeviceInfo } from '../services/api';
import { useAppStore } from '../store/appStore';
import { useShallow } from 'zustand/react/shallow';
import styles from './HeaderBar.module.css';
import { NotificationPanel, useNotifications } from './NotificationPanel';
import ThemeToggle from './ThemeToggle';

const routeTitles: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/device': '设备信息',
  '/models': '模型运行',
  '/datasets': '数据集',
  '/training': '模型训练',
  '/history': '训练历史',
  '/training-compare': '训练对比',
  '/agent': 'Agent 工作台',
  '/chat': 'AI 对话',
  '/inference': '推理测试',
  '/evaluation': '评估对比',
  '/deployment': '部署接入',
  '/knowledge': '知识库',
  '/memory': '智能记忆',
  '/workspace': '工作空间',
  '/project-context': '项目上下文',
  '/cloud-api': '云端 API',
  '/gateway': 'Gateway',
  '/heartbeat': 'Heartbeat',
  '/feedback': '用户反馈',
  '/help': '帮助中心',
};

const { Header } = Layout;

export default function HeaderBar() {
  const location = useLocation();
  const currentTitle = routeTitles[location.pathname] || '';
  const { backendStatus, setDeviceInfo } = useAppStore(useShallow(state => ({
    backendStatus: state.backendStatus,
    setDeviceInfo: state.setDeviceInfo
  })));
  const [loading, setLoading] = useState(false);
  const { notifications, addNotification, markAsRead, markAllAsRead, deleteNotification } =
    useNotifications();

  const fetchDeviceInfo = useCallback(async () => {
    setLoading(true);
    try {
      const info = await getDeviceInfo();
      setDeviceInfo(info);
    } catch {
      // Keep the last known device snapshot; backend connection state is surfaced separately.
    } finally {
      setLoading(false);
    }
  }, [setDeviceInfo]);

  useEffect(() => {
    if (backendStatus === 'connected') {
      fetchDeviceInfo();
    }
  }, [backendStatus, fetchDeviceInfo]);

  // 用 ref 记录上次推送通知时的状态，防止因 React re-render 或 WS 消息
  // 重复触发 onStatusChange 而疯狂弹出"后端已连接"通知
  const prevStatusRef = useRef<string | null>(null);

  useEffect(() => {
    if (backendStatus === prevStatusRef.current) return;
    prevStatusRef.current = backendStatus;

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
  }, [addNotification, backendStatus]);

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
    >
      <Header className={styles.header} role="banner" aria-label="页头">
        <div className={styles.leftSection}>
          {currentTitle && (
            <h1 className={styles.pageTitle}>{currentTitle}</h1>
          )}
        </div>

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
              aria-label="刷新设备状态"
              onClick={fetchDeviceInfo}
              loading={loading}
              size="small"
              style={{ width: 32, height: 32 }}
            />
          </Tooltip>

          <div>
            <Avatar
              icon={<UserOutlined />}
              style={{
                background: 'var(--text-primary)',
                color: 'var(--text-inverse)',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-sm)',
              }}
            />
          </div>
        </Space>
      </Header>
    </motion.div>
  );
}
