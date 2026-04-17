﻿﻿import {
  AppstoreOutlined,
  BookOutlined,
  BulbOutlined,
  CloudOutlined,
  ClusterOutlined,
  CodeOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  FolderOutlined,
  HeartOutlined,
  HistoryOutlined,
  LikeOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Layout, Tooltip } from 'antd';
import { motion } from 'framer-motion';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAppStore } from '../store/appStore';
import styles from './Sidebar.module.css';

const { Sider } = Layout;

interface MenuItem {
  key: string;
  icon: React.ReactNode;
  label: string;
  description?: string;
}

interface MenuGroup {
  label?: string;
  items: MenuItem[];
}

const menuGroups: MenuGroup[] = [
  {
    items: [
      { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘', description: '系统概览' },
      {
        key: '/device',
        icon: <DesktopOutlined />,
        label: '设备信息',
        description: 'GPU / CPU 状态',
      },
    ],
  },
  {
    label: '模型与数据',
    items: [
      { key: '/models', icon: <FolderOutlined />, label: '模型管理', description: '本地模型' },
      {
        key: '/modelhub',
        icon: <CloudOutlined />,
        label: '模型中心',
        description: 'Beta · 外部模型下载',
      },
      { key: '/datasets', icon: <DatabaseOutlined />, label: '数据集', description: '训练数据' },
      {
        key: '/training',
        icon: <PlayCircleOutlined />,
        label: '模型训练',
        description: '微调任务',
      },
      { key: '/history', icon: <HistoryOutlined />, label: '训练历史', description: '任务记录' },
    ],
  },
  {
    label: 'AI 能力',
    items: [
      { key: '/chat', icon: <MessageOutlined />, label: 'AI 对话', description: '智能助手' },
      {
        key: '/inference',
        icon: <ThunderboltOutlined />,
        label: '推理测试',
        description: '模型测试',
      },
      { key: '/knowledge', icon: <BookOutlined />, label: '知识库', description: 'RAG 检索' },
      {
        key: '/memory',
        icon: <BulbOutlined />,
        label: '智能记忆',
        description: 'Beta · 三层记忆系统',
      },
    ],
  },
  {
    label: '开发与集成',
    items: [
      {
        key: '/workspace',
        icon: <AppstoreOutlined />,
        label: '工作空间',
        description: 'Beta · 项目管理',
      },
      {
        key: '/project-context',
        icon: <CodeOutlined />,
        label: '项目上下文',
        description: 'Beta · 代码理解',
      },
      {
        key: '/cloud-api',
        icon: <CloudOutlined />,
        label: '云端 API',
        description: 'API Key 管理',
      },
      {
        key: '/gateway',
        icon: <ClusterOutlined />,
        label: 'Gateway',
        description: 'Experimental · 设备配对与路由',
      },
      {
        key: '/heartbeat',
        icon: <HeartOutlined />,
        label: 'Heartbeat',
        description: 'Experimental · 任务调度验证',
      },
    ],
  },
  {
    label: '其他',
    items: [
      { key: '/feedback', icon: <LikeOutlined />, label: '用户反馈', description: '反馈管理' },
      {
        key: '/help',
        icon: <QuestionCircleOutlined />,
        label: '帮助中心',
        description: '使用指南',
      },
    ],
  },
];

const menuItemVariants = {
  hidden: { opacity: 0, x: -10 },
  show: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: {
      delay: i * 0.03,
      duration: 0.3,
      ease: [0.16, 1, 0.3, 1] as const,
    },
  }),
};

const logoVariants = {
  hidden: { opacity: 0, y: -10 },
  show: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.4,
      ease: [0.16, 1, 0.3, 1] as const,
    },
  },
};

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar, backendStatus } = useAppStore();

  return (
    <Sider
      width={sidebarCollapsed ? 72 : 240}
      collapsible={false}
      collapsed={sidebarCollapsed}
      className={styles.sidebar}
      style={{
        position: 'fixed',
        left: 16,
        top: 16,
        bottom: 16,
        zIndex: 100,
        height: 'calc(100vh - 32px)',
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 'var(--radius-xl)',
        boxShadow: 'var(--shadow-xl)',
      }}
    >
      <motion.div
        variants={logoVariants}
        initial="hidden"
        animate="show"
        className={styles.logoArea}
        style={{
          justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
        }}
      >
        <motion.div
          className={styles.logoIcon}
          onClick={() => navigate('/dashboard')}
          whileTap={{ scale: 0.95 }}
        >
          <img src="/favicon.svg" alt="Logo" style={{ width: 24, height: 24 }} />
        </motion.div>
        {!sidebarCollapsed && (
          <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <h2 className={styles.logoTitle}>Finetune</h2>
            <p className={styles.logoSubtitle}>AI 微调平台</p>
          </motion.div>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        className={styles.statusIndicator}
      >
        <Tooltip
          title={backendStatus === 'connected' ? '后端服务运行正常' : '后端服务未连接'}
          placement="right"
        >
          <div
            className={styles.statusBadge}
            style={{
              justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
              background:
                backendStatus === 'connected'
                  ? 'rgba(91, 138, 114, 0.1)'
                  : 'rgba(196, 92, 72, 0.1)',
              color: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)',
                display: 'inline-block',
                position: 'relative',
                boxShadow: backendStatus === 'connected' ? '0 0 10px var(--success)' : 'none',
              }}
            >
              {backendStatus === 'connected' && (
                <span
                  style={{
                    position: 'absolute',
                    inset: -4,
                    borderRadius: '50%',
                    border: `2px solid ${'var(--success)'}`,
                    animation: 'pulse-ring 2s cubic-bezier(0.215, 0.61, 0.355, 1) infinite',
                  }}
                />
              )}
            </span>
            {!sidebarCollapsed && (
              <span style={{ whiteSpace: 'nowrap' }}>
                {backendStatus === 'connected' ? 'ONLINE' : 'OFFLINE'}
              </span>
            )}
          </div>
        </Tooltip>
      </motion.div>

      <div className={styles.menuWrapper}>
        {menuGroups.map((group, groupIndex) => {
          const allItems = group.items;
          return (
            <div key={groupIndex}>
              {group.label && !sidebarCollapsed && (
                <div className={styles.menuGroupLabel}>{group.label}</div>
              )}
              {group.label && sidebarCollapsed && groupIndex > 0 && (
                <div className={styles.menuGroupDivider} />
              )}
              {allItems.map((item, index) => {
                const isActive = location.pathname === item.key;
                const globalIndex =
                  menuGroups.slice(0, groupIndex).reduce((acc, g) => acc + g.items.length, 0) +
                  index;
                return (
                  <Tooltip
                    key={item.key}
                    title={sidebarCollapsed ? item.label : undefined}
                    placement="right"
                  >
                    <motion.div
                      custom={globalIndex}
                      variants={menuItemVariants}
                      initial="hidden"
                      animate="show"
                      className={`${styles.menuItem} ${isActive ? styles.menuItemActive : ''}`}
                      onClick={() => navigate(item.key)}
                      whileHover={{ x: 4 }}
                      whileTap={{ scale: 0.98 }}
                      style={{
                        justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                      }}
                    >
                      {isActive && (
                        <motion.span
                          layoutId="activeIndicator"
                          className={styles.activeIndicator}
                        />
                      )}

                      <span
                        className={styles.menuIcon}
                        style={{
                          color: isActive ? 'var(--accent-primary)' : 'inherit',
                          transform: isActive ? 'scale(1.1)' : 'scale(1)',
                        }}
                      >
                        {item.icon}
                      </span>

                      {!sidebarCollapsed && (
                        <div style={{ flex: 1, overflow: 'hidden' }}>
                          <div className={styles.menuLabel}>{item.label}</div>
                          {item.description && (
                            <div className={styles.menuDesc}>{item.description}</div>
                          )}
                        </div>
                      )}
                    </motion.div>
                  </Tooltip>
                );
              })}
            </div>
          );
        })}
      </div>

      <motion.div
        className={styles.collapseBtn}
        onClick={toggleSidebar}
        whileTap={{ scale: 0.98 }}
        style={{
          justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
        }}
      >
        <motion.span
          animate={{ rotate: sidebarCollapsed ? 180 : 0 }}
          transition={{ duration: 0.3 }}
          style={{ fontSize: 16 }}
        >
          {sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </motion.span>
        {!sidebarCollapsed && <span style={{ whiteSpace: 'nowrap' }}>收起侧边栏</span>}
      </motion.div>

      <style>{`
        @keyframes pulse-ring {
          0% {
            transform: scale(0.8);
            opacity: 1;
          }
          100% {
            transform: scale(1.5);
            opacity: 0;
          }
        }
      `}</style>
    </Sider>
  );
}
