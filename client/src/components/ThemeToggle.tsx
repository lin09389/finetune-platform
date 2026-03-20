import { Dropdown } from 'antd'
import { MoonOutlined, SunOutlined, LaptopOutlined } from '@ant-design/icons'
import { useAppStore, type ThemeMode } from '../store/appStore'

export default function ThemeToggle() {
  const { themeMode, setThemeMode } = useAppStore()

  const getIcon = () => {
    switch (themeMode) {
      case 'dark':
        return <MoonOutlined />
      case 'light':
        return <SunOutlined />
      default:
        return <LaptopOutlined />
    }
  }

  const items = [
    {
      key: 'light',
      label: '浅色模式',
      icon: <SunOutlined />
    },
    {
      key: 'dark',
      label: '深色模式',
      icon: <MoonOutlined />
    },
    {
      key: 'system',
      label: '跟随系统',
      icon: <LaptopOutlined />
    }
  ]

  return (
    <Dropdown
      menu={{
        items,
        onClick: ({ key }) => setThemeMode(key as ThemeMode),
        selectedKeys: [themeMode]
      }}
      trigger={['click']}
    >
      <div style={{
        padding: '8px 12px',
        cursor: 'pointer',
        borderRadius: 8,
        display: 'flex',
        alignItems: 'center',
        gap: 8
      }}>
        {getIcon()}
        <span style={{ fontSize: 14 }}>{themeMode === 'light' ? '浅色' : themeMode === 'dark' ? '深色' : '系统'}</span>
      </div>
    </Dropdown>
  )
}
