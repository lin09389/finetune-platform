import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';
import { Layout, Tooltip } from 'antd';
import { motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';
import { type ApiInfoCapabilityPayload, isExperimentalEnabled, tierLabel } from '../capability/tiers';
import {
  getNavigationGroups,
  getRouteCapabilityTier,
  isRouteVisible,
} from '../navigation/routeMetadata';
import { apiClient } from '../services/api';
import { useAppStore } from '../store/appStore';
import styles from './Sidebar.module.css';

const { Sider } = Layout;

const menuItemVariants = {
  hidden: { opacity: 0, x: -10 },
  show: (index: number) => ({
    opacity: 1,
    x: 0,
    transition: { delay: index * 0.03, duration: 0.3, ease: [0.23, 1, 0.32, 1] as const },
  }),
};

const logoVariants = {
  hidden: { opacity: 0, y: -10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.23, 1, 0.32, 1] as const } },
};

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { sidebarCollapsed, toggleSidebar, backendStatus } = useAppStore(useShallow((state) => ({
    sidebarCollapsed: state.sidebarCollapsed,
    toggleSidebar: state.toggleSidebar,
    backendStatus: state.backendStatus,
  })));
  const [apiInfo, setApiInfo] = useState<ApiInfoCapabilityPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (backendStatus !== 'connected') {
      setApiInfo(null);
      return undefined;
    }
    apiClient.get('/api/info')
      .then((response) => { if (!cancelled) setApiInfo(response.data as ApiInfoCapabilityPayload); })
      .catch(() => { if (!cancelled) setApiInfo(null); });
    return () => { cancelled = true; };
  }, [backendStatus]);

  const experimentalEnabled = isExperimentalEnabled(apiInfo);
  const visibleGroups = useMemo(
    () => getNavigationGroups('sidebar')
      .map((group) => ({ ...group, items: group.items.filter((item) => isRouteVisible(item.path, experimentalEnabled)) }))
      .filter((group) => group.items.length > 0),
    [experimentalEnabled],
  );

  const onActivateKey = (event: React.KeyboardEvent, action: () => void) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      action();
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
      style={{ position: 'fixed', left: 16, top: 16, bottom: 16, zIndex: 100, height: 'calc(100vh - 32px)', display: 'flex', flexDirection: 'column', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)' }}
    >
      <motion.div variants={logoVariants} initial="hidden" animate="show" className={styles.logoArea} style={{ justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}>
        <motion.div className={styles.logoIcon} role="button" tabIndex={0} aria-label="返回仪表盘" onClick={() => navigate('/dashboard')} onKeyDown={(event) => onActivateKey(event, () => navigate('/dashboard'))} whileTap={{ opacity: 0.85 }}>
          <img src="/favicon.svg" alt="Logo" style={{ width: 24, height: 24 }} />
        </motion.div>
        {!sidebarCollapsed && <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }} style={{ overflow: 'hidden' }}>
          <h2 className={styles.logoTitle}>Finetune</h2>
          <p className={styles.logoSubtitle}>AI 微调平台</p>
        </motion.div>}
      </motion.div>

      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }} className={styles.statusIndicator}>
        <Tooltip title={backendStatus === 'connected' ? '后端服务运行正常' : '后端服务未连接'} placement="right">
          <div className={styles.statusBadge} role="status" aria-label={backendStatus === 'connected' ? '后端服务：已连接' : '后端服务：未连接'} style={{ justifyContent: sidebarCollapsed ? 'center' : 'flex-start', background: backendStatus === 'connected' ? 'var(--success-light)' : 'var(--error-light)', color: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)', display: 'inline-block' }} />
            {!sidebarCollapsed && <span style={{ whiteSpace: 'nowrap' }}>{backendStatus === 'connected' ? 'ONLINE' : 'OFFLINE'}</span>}
          </div>
        </Tooltip>
      </motion.div>

      <div className={styles.menuWrapper}>
        {visibleGroups.map((group, groupIndex) => (
          <div key={group.id}>
            {!sidebarCollapsed && <div className={styles.menuGroupLabel}>{group.label}</div>}
            {sidebarCollapsed && groupIndex > 0 && <div className={styles.menuGroupDivider} />}
            {group.items.map((item, index) => {
              const isActive = location.pathname === item.path;
              const tier = getRouteCapabilityTier(item.path);
              const globalIndex = visibleGroups.slice(0, groupIndex).reduce((total, current) => total + current.items.length, 0) + index;
              return <Tooltip key={item.path} title={sidebarCollapsed ? item.label : undefined} placement="right">
                <motion.div custom={globalIndex} variants={menuItemVariants} initial="hidden" animate="show" className={`${styles.menuItem} ${isActive ? styles.menuItemActive : ''}`} role="button" tabIndex={0} aria-current={isActive ? 'page' : undefined} aria-label={item.label} data-capability-tier={tier ?? 'none'} onClick={() => navigate(item.path)} onKeyDown={(event) => onActivateKey(event, () => navigate(item.path))} whileTap={{ opacity: 0.85 }} style={{ justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}>
                  {isActive && <motion.span layoutId="activeIndicator" className={styles.activeIndicator} />}
                  <span className={styles.menuIcon} style={{ color: isActive ? 'var(--accent-primary)' : 'inherit', transform: isActive ? 'scale(1.05)' : 'scale(1)' }}>{item.icon}</span>
                  {!sidebarCollapsed && <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div className={styles.menuLabelRow}>
                      <div className={styles.menuLabel}>{item.label}</div>
                      {tier && tier !== 'ga' && <span className={tier === 'beta' ? styles.tierBadgeBeta : styles.tierBadgeExp} data-testid={`tier-badge-${tier}`}>{tierLabel(tier)}</span>}
                    </div>
                    {item.description && <div className={styles.menuDesc}>{item.description}</div>}
                  </div>}
                </motion.div>
              </Tooltip>;
            })}
          </div>
        ))}
      </div>

      <motion.div className={styles.collapseBtn} role="button" tabIndex={0} aria-label={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'} aria-expanded={!sidebarCollapsed} onClick={toggleSidebar} onKeyDown={(event) => onActivateKey(event, toggleSidebar)} whileTap={{ opacity: 0.85 }} style={{ justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}>
        <motion.span animate={{ rotate: sidebarCollapsed ? 180 : 0 }} transition={{ duration: 0.3 }} style={{ fontSize: 16 }}>{sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}</motion.span>
        {!sidebarCollapsed && <span style={{ whiteSpace: 'nowrap' }}>收起侧边栏</span>}
      </motion.div>
    </Sider>
  );
}
