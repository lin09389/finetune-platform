import {
  AppstoreOutlined,
  ApiOutlined,
  BookOutlined,
  BulbOutlined,
  CloseOutlined,
  CloudOutlined,
  CodeOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  FileSearchOutlined,
  FolderOutlined,
  HistoryOutlined,
  LineChartOutlined,
  MenuOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Drawer } from 'antd';
import { motion } from 'framer-motion';
import React, { memo, useCallback, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';
import { useResponsive } from '../../hooks/useResponsive';
import { useAppStore } from '../../store/appStore';

interface NavItem {
  key: string;
  icon: React.ReactNode;
  label: string;
  description?: string;
  category?: 'main' | 'secondary';
}

const navItems: NavItem[] = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘', category: 'main' },
  { key: '/training', icon: <PlayCircleOutlined />, label: '训练', category: 'main' },
  { key: '/chat', icon: <MessageOutlined />, label: '对话', category: 'main' },
  { key: '/device', icon: <DesktopOutlined />, label: '设备信息', category: 'secondary' },
  { key: '/models', icon: <FolderOutlined />, label: '模型管理', category: 'secondary' },
  { key: '/modelhub', icon: <CloudOutlined />, label: '模型中心', category: 'secondary' },
  { key: '/datasets', icon: <DatabaseOutlined />, label: '数据集', category: 'secondary' },
  { key: '/evaluation', icon: <FileSearchOutlined />, label: '评估对比', category: 'secondary' },
  { key: '/deployment', icon: <ApiOutlined />, label: '部署接入', category: 'secondary' },
  { key: '/knowledge', icon: <BookOutlined />, label: '知识库', category: 'secondary' },
  { key: '/memory', icon: <BulbOutlined />, label: '智能记忆', category: 'secondary' },
  { key: '/workspace', icon: <AppstoreOutlined />, label: '工作空间', category: 'secondary' },
  { key: '/inference', icon: <ThunderboltOutlined />, label: '推理测试', category: 'secondary' },
  { key: '/history', icon: <HistoryOutlined />, label: '训练历史', category: 'secondary' },
  { key: '/training-compare', icon: <LineChartOutlined />, label: '训练对比', category: 'secondary' },
  { key: '/project-context', icon: <CodeOutlined />, label: '项目上下文', category: 'secondary' },
  { key: '/cloud-api', icon: <CloudOutlined />, label: '云端 API', category: 'secondary' },
];

const bottomNavItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '首页' },
  { key: '/training', icon: <PlayCircleOutlined />, label: '训练' },
  { key: '/chat', icon: <MessageOutlined />, label: '对话' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
];

const MobileNav: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isMobile, isTablet } = useResponsive();
  const { backendStatus } = useAppStore(useShallow(state => ({
    backendStatus: state.backendStatus
  })));
  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleNavigate = useCallback(
    (key: string) => {
      navigate(key);
      setDrawerOpen(false);
    },
    [navigate],
  );

  if (!isMobile && !isTablet) {
    return null;
  }

  return (
    <>
      <Button
        type="text"
        icon={<MenuOutlined style={{ fontSize: 20 }} />}
        onClick={() => setDrawerOpen(true)}
        style={{
          position: 'fixed',
          top: 8,
          left: 8,
          zIndex: 120,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 44,
          height: 44,
          borderRadius: 'var(--radius-md)',
          background: 'var(--bg-secondary)',
          color: 'var(--text-primary)',
          boxShadow: 'var(--shadow-sm)',
        }}
        aria-label="打开菜单"
      />

      <Drawer
        placement="left"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={280}
        closable={false}
        styles={{
          body: { padding: 0 },
          header: { display: 'none' },
        }}
        style={{
          background: 'var(--bg-secondary)',
        }}
      >
        <div
          style={{
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              padding: '20px 16px',
              borderBottom: '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--text-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 18,
                  color: '#fff',
                }}
              >
                <ThunderboltOutlined />
              </div>
              <div>
                <h2
                  style={{
                    margin: 0,
                    fontSize: 'var(--text-base)',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                  }}
                >
                  Finetune
                </h2>
                <p
                  style={{
                    margin: 0,
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  AI 微调平台
                </p>
              </div>
            </div>
            <Button
              type="text"
              icon={<CloseOutlined />}
              onClick={() => setDrawerOpen(false)}
              style={{
                color: 'var(--text-secondary)',
              }}
              aria-label="关闭菜单"
            />
          </div>

          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--border-color)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '6px 10px',
                borderRadius: 'var(--radius-md)',
                background:
                  backendStatus === 'connected' ? 'var(--success-light)' : 'var(--error-light)',
                fontSize: 'var(--text-sm)',
                color: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)',
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)',
                }}
              />
              {backendStatus === 'connected' ? '服务正常' : '未连接'}
            </div>
          </div>

          <div
            style={{
              flex: 1,
              overflow: 'auto',
              padding: '8px',
            }}
          >
            <div style={{ marginBottom: 8 }}>
              <div
                style={{
                  padding: '8px 12px',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 500,
                  color: 'var(--text-tertiary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                主要功能
              </div>
              {navItems
                .filter((item) => item.category === 'main')
                .map((item) => (
                  <NavItem
                    key={item.key}
                    item={item}
                    isActive={location.pathname === item.key}
                    onClick={() => handleNavigate(item.key)}
                  />
                ))}
            </div>

            <div>
              <div
                style={{
                  padding: '8px 12px',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 500,
                  color: 'var(--text-tertiary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                其他功能
              </div>
              {navItems
                .filter((item) => item.category === 'secondary')
                .map((item) => (
                  <NavItem
                    key={item.key}
                    item={item}
                    isActive={location.pathname === item.key}
                    onClick={() => handleNavigate(item.key)}
                  />
                ))}
            </div>
          </div>

          <div
            style={{
              padding: 16,
              borderTop: '1px solid var(--border-color)',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <Avatar
              size={36}
              style={{ background: 'var(--text-primary)' }}
              icon={<SettingOutlined />}
            />
            <div>
              <div
                style={{
                  fontSize: 'var(--text-sm)',
                  fontWeight: 500,
                  color: 'var(--text-primary)',
                }}
              >
                设置
              </div>
              <div
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-tertiary)',
                }}
              >
                主题、语言等
              </div>
            </div>
          </div>
        </div>
      </Drawer>
    </>
  );
};

const NavItem: React.FC<{
  item: NavItem;
  isActive: boolean;
  onClick: () => void;
}> = memo(({ item, isActive, onClick }) => (
  <motion.div
    whileTap={{ scale: 0.98 }}
    onClick={onClick}
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '10px 12px',
      margin: '2px 0',
      borderRadius: 'var(--radius-md)',
      cursor: 'pointer',
      color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
      background: isActive ? 'var(--bg-hover)' : 'transparent',
      transition: 'all 0.15s ease',
      position: 'relative',
    }}
  >
    {isActive && (
      <span
        style={{
          position: 'absolute',
          left: 0,
          top: '50%',
          transform: 'translateY(-50%)',
          width: 3,
          height: 16,
          background: 'var(--accent-primary)',
          borderRadius: '0 2px 2px 0',
        }}
      />
    )}
    <span
      style={{
        fontSize: 16,
        color: isActive ? 'var(--accent-primary)' : 'inherit',
      }}
    >
      {item.icon}
    </span>
    <span
      style={{
        fontSize: 'var(--text-sm)',
        fontWeight: isActive ? 600 : 500,
      }}
    >
      {item.label}
    </span>
  </motion.div>
));

NavItem.displayName = 'NavItem';

export const MobileBottomNav: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isMobile } = useResponsive();

  if (!isMobile) {
    return null;
  }

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        height: 56,
        background: 'var(--bg-secondary)',
        borderTop: '1px solid var(--border-color)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-around',
        zIndex: 100,
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
    >
      {bottomNavItems.map((item) => {
        const isActive = location.pathname === item.key;
        return (
          <motion.div
            key={item.key}
            whileTap={{ scale: 0.95 }}
            onClick={() => navigate(item.key)}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '4px 12px',
              cursor: 'pointer',
              minWidth: 64,
              minHeight: 44,
            }}
          >
            <span
              style={{
                fontSize: 20,
                color: isActive ? 'var(--accent-primary)' : 'var(--text-tertiary)',
                marginBottom: 2,
              }}
            >
              {item.icon}
            </span>
            <span
              style={{
                fontSize: 'var(--text-xs)',
                color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
                fontWeight: isActive ? 500 : 400,
              }}
            >
              {item.label}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
};

export default memo(MobileNav);
