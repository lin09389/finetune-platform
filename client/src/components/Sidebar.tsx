import {
  AppstoreOutlined,
  BookOutlined,
  BulbOutlined,
  CloudOutlined,
  ClusterOutlined,
  CodeOutlined,
  ApiOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  FileSearchOutlined,
  FolderOutlined,
  HeartOutlined,
  HistoryOutlined,
  LikeOutlined,
  LineChartOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  RobotOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Layout, Tooltip } from 'antd';
import { motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';
import {
  ApiInfoCapabilityPayload,
  CapabilityTier,
  isExperimentalEnabled,
  ROUTE_CAPABILITY,
  tierLabel,
} from '../capability/tiers';
import { apiClient } from '../services/api';
import { useAppStore } from '../store/appStore';
import styles from './Sidebar.module.css';

const { Sider } = Layout;

interface MenuItem {
  key: string;
  icon: React.ReactNode;
  label: string;
  description?: string;
  tier?: CapabilityTier;
}

interface MenuGroup {
  label?: string;
  tier?: CapabilityTier;
  items: MenuItem[];
}

const menuGroups: MenuGroup[] = [
  {
    label: '核心功能 (GA)',
    tier: 'ga',
    items: [
      { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘', description: '系统概览', tier: 'ga' },
      {
        key: '/device',
        icon: <DesktopOutlined />,
        label: '设备信息',
        description: 'GPU / CPU 状态',
        tier: 'ga',
      },
      { key: '/models', icon: <FolderOutlined />, label: '模型运行', description: '接入与 Agent', tier: 'ga' },
      { key: '/datasets', icon: <DatabaseOutlined />, label: '数据集', description: '训练数据', tier: 'ga' },
      {
        key: '/training',
        icon: <PlayCircleOutlined />,
        label: '模型训练',
        description: '微调任务',
        tier: 'ga',
      },
      { key: '/history', icon: <HistoryOutlined />, label: '训练历史', description: '任务记录', tier: 'ga' },
      {
        key: '/training-compare',
        icon: <LineChartOutlined />,
        label: '训练对比',
        description: '指标横评',
        tier: 'ga',
      },
      { key: '/agent', icon: <RobotOutlined />, label: 'Agent 工作台', description: '任务执行', tier: 'ga' },
      { key: '/chat', icon: <MessageOutlined />, label: 'AI 对话', description: '纯聊天', tier: 'ga' },
      {
        key: '/inference',
        icon: <ThunderboltOutlined />,
        label: '推理测试',
        description: '模型测试',
        tier: 'ga',
      },
      {
        key: '/evaluation',
        icon: <FileSearchOutlined />,
        label: '评估对比',
        description: '效果验证',
        tier: 'ga',
      },
      {
        key: '/deployment',
        icon: <ApiOutlined />,
        label: '部署接入',
        description: '应用集成',
        tier: 'ga',
      },
      { key: '/knowledge', icon: <BookOutlined />, label: '知识库', description: 'RAG 检索', tier: 'ga' },
    ],
  },
  {
    label: 'Beta 功能',
    tier: 'beta',
    items: [
      {
        key: '/memory',
        icon: <BulbOutlined />,
        label: '智能记忆',
        description: '三层记忆系统',
        tier: 'beta',
      },
      {
        key: '/workspace',
        icon: <AppstoreOutlined />,
        label: '工作空间',
        description: '项目管理',
        tier: 'beta',
      },
      {
        key: '/project-context',
        icon: <CodeOutlined />,
        label: '项目上下文',
        description: '代码理解',
        tier: 'beta',
      },
    ],
  },
  {
    label: '实验性 (Experimental)',
    tier: 'experimental',
    items: [
      {
        key: '/gateway',
        icon: <ClusterOutlined />,
        label: 'Gateway',
        description: '设备配对与路由',
        tier: 'experimental',
      },
      {
        key: '/heartbeat',
        icon: <HeartOutlined />,
        label: 'Heartbeat',
        description: '任务调度验证',
        tier: 'experimental',
      },
    ],
  },
  {
    label: '支持',
    items: [
      {
        key: '/cloud-api',
        icon: <CloudOutlined />,
        label: '云端 API',
        description: 'API Key 管理',
        // Always-on auxiliary (api.cloud_chat), not gated by ENABLE_EXPERIMENTAL_CAPABILITIES
        tier: 'beta',
      },
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
      ease: [0.23, 1, 0.32, 1] as const,
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
      ease: [0.23, 1, 0.32, 1] as const,
    },
  },
};

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { sidebarCollapsed, toggleSidebar, backendStatus } = useAppStore(useShallow(state => ({
    sidebarCollapsed: state.sidebarCollapsed,
    toggleSidebar: state.toggleSidebar,
    backendStatus: state.backendStatus
  })));
  const [apiInfo, setApiInfo] = useState<ApiInfoCapabilityPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (backendStatus !== 'connected') {
      // Clear stale apiInfo so experimental menu doesn't stay visible after
      // the backend disconnects.
      setApiInfo(null);
      return;
    }
    apiClient
      .get('/api/info')
      .then(res => {
        if (!cancelled) {
          setApiInfo(res.data as ApiInfoCapabilityPayload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setApiInfo(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [backendStatus]);

  const experimentalOn = isExperimentalEnabled(apiInfo);

  const visibleGroups = useMemo(() => {
    return menuGroups
      .map(group => {
        if (group.tier === 'experimental' && !experimentalOn) {
          return { ...group, items: [] as MenuItem[] };
        }
        const items = group.items.filter(item => {
          const meta = ROUTE_CAPABILITY[item.key];
          if (meta?.tier === 'experimental' && !experimentalOn) {
            return false;
          }
          return true;
        });
        return { ...group, items };
      })
      .filter(g => g.items.length > 0 || !g.tier);
  }, [experimentalOn]);

  // Activate a click action on Enter / Space for keyboard users on role="button"
  // elements (menu items, logo, collapse button). Native <button>/<a> would handle
  // this automatically, but we keep motion.div for animation fidelity.
  const onActivateKey = (e: React.KeyboardEvent, fn: () => void) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fn();
    }
  };

  return (
    <Sider
      width={sidebarCollapsed ? 72 : 240}
      collapsible={false}
      collapsed={sidebarCollapsed}
      className={styles.sidebar}
      role="navigation"
      aria-label="主导航"
      style={{
        position: 'fixed',
        left: 16,
        top: 16,
        bottom: 16,
        zIndex: 100,
        height: 'calc(100vh - 32px)',
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-lg)',
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
          role="button"
          tabIndex={0}
          aria-label="返回仪表盘"
          onClick={() => navigate('/dashboard')}
          onKeyDown={(e) => onActivateKey(e, () => navigate('/dashboard'))}
          whileTap={{ opacity: 0.85 }}
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
            role="status"
            aria-label={backendStatus === 'connected' ? '后端服务：已连接' : '后端服务：未连接'}
            style={{
              justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
              background:
                backendStatus === 'connected'
                  ? 'var(--success-light)'
                  : 'var(--error-light)',
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
              }}
            />
            {!sidebarCollapsed && (
              <span style={{ whiteSpace: 'nowrap' }}>
                {backendStatus === 'connected' ? 'ONLINE' : 'OFFLINE'}
              </span>
            )}
          </div>
        </Tooltip>
      </motion.div>

      <div className={styles.menuWrapper}>
        {visibleGroups.map((group, groupIndex) => {
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
                const tier = item.tier || ROUTE_CAPABILITY[item.key]?.tier;
                const globalIndex =
                  visibleGroups.slice(0, groupIndex).reduce((acc, g) => acc + g.items.length, 0) +
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
                      role="button"
                      tabIndex={0}
                      aria-current={isActive ? 'page' : undefined}
                      aria-label={item.label}
                      data-capability-tier={tier || 'none'}
                      onClick={() => navigate(item.key)}
                      onKeyDown={(e) => onActivateKey(e, () => navigate(item.key))}
                      whileTap={{ opacity: 0.85 }}
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
                          transform: isActive ? 'scale(1.05)' : 'scale(1)',
                        }}
                      >
                        {item.icon}
                      </span>

                      {!sidebarCollapsed && (
                        <div style={{ flex: 1, overflow: 'hidden' }}>
                          <div className={styles.menuLabelRow}>
                            <div className={styles.menuLabel}>{item.label}</div>
                            {tier && tier !== 'ga' && (
                              <span
                                className={
                                  tier === 'beta' ? styles.tierBadgeBeta : styles.tierBadgeExp
                                }
                                data-testid={`tier-badge-${tier}`}
                              >
                                {tierLabel(tier)}
                              </span>
                            )}
                          </div>
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
        role="button"
        tabIndex={0}
        aria-label={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
        aria-expanded={!sidebarCollapsed}
        onClick={toggleSidebar}
        onKeyDown={(e) => onActivateKey(e, toggleSidebar)}
        whileTap={{ opacity: 0.85 }}
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

    </Sider>
  );
}
