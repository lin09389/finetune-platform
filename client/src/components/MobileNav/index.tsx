import { CloseOutlined, MenuOutlined, SettingOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Avatar, Button, Drawer } from 'antd';
import { motion } from 'framer-motion';
import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';
import { type ApiInfoCapabilityPayload, isExperimentalEnabled, tierLabel } from '../../capability/tiers';
import { useResponsive } from '../../hooks/useResponsive';
import { getBottomNavigationItems, getNavigationGroups, getRouteCapabilityTier, getRouteLabel, isRouteVisible, type RouteMetadata } from '../../navigation/routeMetadata';
import { apiClient } from '../../services/api';
import { useAppStore } from '../../store/appStore';

const MobileNav: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isMobile, isTablet } = useResponsive();
  const { backendStatus } = useAppStore(useShallow((state) => ({ backendStatus: state.backendStatus })));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [apiInfo, setApiInfo] = useState<ApiInfoCapabilityPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (backendStatus !== 'connected') {
      setApiInfo(null);
      return undefined;
    }
    apiClient.get('/api/info').then((response) => { if (!cancelled) setApiInfo(response.data as ApiInfoCapabilityPayload); }).catch(() => { if (!cancelled) setApiInfo(null); });
    return () => { cancelled = true; };
  }, [backendStatus]);

  const experimentalEnabled = isExperimentalEnabled(apiInfo);
  const visibleGroups = useMemo(
    () => getNavigationGroups('mobile')
      .map((group) => ({ ...group, items: group.items.filter((item) => isRouteVisible(item.path, experimentalEnabled)) }))
      .filter((group) => group.items.length > 0),
    [experimentalEnabled],
  );
  const handleNavigate = useCallback((path: string) => { navigate(path); setDrawerOpen(false); }, [navigate]);

  if (!isMobile && !isTablet) return null;

  return <>
    <Button type="text" icon={<MenuOutlined style={{ fontSize: 20 }} />} onClick={() => setDrawerOpen(true)} style={{ position: 'fixed', top: 8, left: 8, zIndex: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', width: 44, height: 44, borderRadius: 'var(--radius-md)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', boxShadow: 'var(--shadow-sm)' }} aria-label="打开菜单" />
    <Drawer placement="left" open={drawerOpen} onClose={() => setDrawerOpen(false)} width={280} closable={false} styles={{ body: { padding: 0 }, header: { display: 'none' } }} style={{ background: 'var(--bg-secondary)' }}>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '20px 16px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: 'var(--radius-md)', background: 'var(--text-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: 'var(--text-inverse)' }}><ThunderboltOutlined /></div>
            <div><h2 style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--text-primary)' }}>Finetune</h2><p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>AI 微调平台</p></div>
          </div>
          <Button type="text" icon={<CloseOutlined />} onClick={() => setDrawerOpen(false)} style={{ color: 'var(--text-secondary)' }} aria-label="关闭菜单" />
        </div>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 10px', borderRadius: 'var(--radius-md)', background: backendStatus === 'connected' ? 'var(--success-light)' : 'var(--error-light)', fontSize: 'var(--text-sm)', color: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)' }} role="status" aria-label={backendStatus === 'connected' ? '后端服务：已连接' : '后端服务：未连接'}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)' }} />{backendStatus === 'connected' ? '服务正常' : '未连接'}
          </div>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '8px' }} role="navigation" aria-label="移动端导航">
          {visibleGroups.map((group) => <div key={group.id} style={{ marginBottom: 8 }}>
            <div style={{ padding: '8px 12px', fontSize: 'var(--text-xs)', fontWeight: 500, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{group.label}</div>
            {group.items.map((item) => <NavItem key={item.path} item={item} isActive={location.pathname === item.path} onClick={() => handleNavigate(item.path)} />)}
          </div>)}
        </div>
        <div style={{ padding: 16, borderTop: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: 12 }}>
          <Avatar size={36} style={{ background: 'var(--text-primary)' }} icon={<SettingOutlined />} />
          <div><div style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>设置</div><div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>主题、语言等</div></div>
        </div>
      </div>
    </Drawer>
  </>;
};

const NavItem: React.FC<{ item: RouteMetadata; isActive: boolean; onClick: () => void }> = memo(({ item, isActive, onClick }) => {
  const tier = getRouteCapabilityTier(item.path);
  return <motion.div whileTap={{ opacity: 0.85 }} onClick={onClick} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onClick(); } }} role="button" tabIndex={0} aria-current={isActive ? 'page' : undefined} aria-label={item.label} data-capability-tier={tier ?? 'none'} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', margin: '2px 0', borderRadius: 'var(--radius-md)', cursor: 'pointer', color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)', background: isActive ? 'var(--bg-hover)' : 'transparent', transition: 'all 0.15s ease', position: 'relative' }}>
    {isActive && <span style={{ position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)', width: 3, height: 16, background: 'var(--accent-primary)', borderRadius: '0 2px 2px 0' }} />}
    <span style={{ fontSize: 16, color: isActive ? 'var(--accent-primary)' : 'inherit' }}>{item.icon}</span>
    <span style={{ fontSize: 'var(--text-sm)', fontWeight: isActive ? 600 : 500 }}>{item.label}</span>
    {tier && tier !== 'ga' && <span style={{ marginLeft: 'auto', color: tier === 'beta' ? 'var(--warning)' : 'var(--error)', fontSize: 'var(--text-xs)', fontWeight: 600 }}>{tierLabel(tier)}</span>}
  </motion.div>;
});

NavItem.displayName = 'NavItem';

export const MobileBottomNav: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isMobile } = useResponsive();
  if (!isMobile) return null;
  return <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: 56, background: 'var(--bg-secondary)', borderTop: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-around', zIndex: 100, paddingBottom: 'env(safe-area-inset-bottom)' }} role="navigation" aria-label="底部导航">
    {getBottomNavigationItems().map((item) => {
      const isActive = location.pathname === item.path;
      return <motion.div key={item.path} whileTap={{ opacity: 0.85 }} onClick={() => navigate(item.path)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); navigate(item.path); } }} role="button" tabIndex={0} aria-current={isActive ? 'page' : undefined} aria-label={getRouteLabel(item, 'bottom')} data-capability-tier={getRouteCapabilityTier(item.path) ?? 'none'} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '4px 12px', cursor: 'pointer', minWidth: 64, minHeight: 44 }}>
        <span style={{ fontSize: 20, color: isActive ? 'var(--accent-primary)' : 'var(--text-tertiary)', marginBottom: 2 }}>{item.icon}</span>
        <span style={{ fontSize: 'var(--text-xs)', color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)', fontWeight: isActive ? 500 : 400 }}>{getRouteLabel(item, 'bottom')}</span>
      </motion.div>;
    })}
  </div>;
};

export default memo(MobileNav);
