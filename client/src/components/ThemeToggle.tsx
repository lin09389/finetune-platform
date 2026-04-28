import { LaptopOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons';
import { Dropdown } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore, type ThemeMode } from '../store/appStore';

export default function ThemeToggle() {
  const { themeMode, setThemeMode } = useAppStore(useShallow(state => ({
    themeMode: state.themeMode,
    setThemeMode: state.setThemeMode
  })));

  const getIcon = () => {
    switch (themeMode) {
      case 'dark':
        return <MoonOutlined key="dark" />;
      case 'light':
        return <SunOutlined key="light" />;
      default:
        return <LaptopOutlined key="system" />;
    }
  };

  const items = [
    {
      key: 'light',
      label: '浅色模式',
      icon: <SunOutlined />,
    },
    {
      key: 'dark',
      label: '深色模式',
      icon: <MoonOutlined />,
    },
    {
      key: 'system',
      label: '跟随系统',
      icon: <LaptopOutlined />,
    },
  ];

  return (
    <Dropdown
      menu={{
        items,
        onClick: ({ key }) => setThemeMode(key as ThemeMode),
        selectedKeys: [themeMode],
      }}
      trigger={['click']}
      overlayClassName="theme-dropdown"
    >
      <div className="flex items-center gap-2 px-3 py-2 cursor-pointer rounded-lg hover:bg-bg-hover transition-colors duration-base border border-transparent hover:border-glass-border">
        <div className="relative w-4 h-4 flex items-center justify-center overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={themeMode}
              initial={{ y: 10, opacity: 0, rotate: -45 }}
              animate={{ y: 0, opacity: 1, rotate: 0 }}
              exit={{ y: -10, opacity: 0, rotate: 45 }}
              transition={{ duration: 0.2, ease: 'easeInOut' }}
              className="absolute inset-0 flex items-center justify-center"
            >
              {getIcon()}
            </motion.div>
          </AnimatePresence>
        </div>
        <span className="text-sm font-medium text-text-secondary">
          {themeMode === 'light' ? '浅色' : themeMode === 'dark' ? '深色' : '系统'}
        </span>
      </div>
    </Dropdown>
  );
}
