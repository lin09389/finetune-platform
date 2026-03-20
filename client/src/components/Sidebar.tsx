import { Layout, Tooltip } from 'antd'
import { useNavigate, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  DesktopOutlined,
  FolderOutlined,
  DatabaseOutlined,
  PlayCircleOutlined,
  MessageOutlined,
  HistoryOutlined,
  DashboardOutlined,
  BookOutlined,
  AppstoreOutlined,
  CloudOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ThunderboltOutlined,
  CodeOutlined,
  ToolOutlined,
  BulbOutlined,
  ApiOutlined,
  ClusterOutlined,
  HeartOutlined,
  LikeOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { useState, useEffect } from 'react'

const { Sider } = Layout

interface MenuItem {
  key: string
  icon: React.ReactNode
  label: string
  description?: string
}

const menuItems: MenuItem[] = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘', description: '系统概览' },
  { key: '/device', icon: <DesktopOutlined />, label: '设备信息', description: 'GPU/CPU状态' },
  { key: '/models', icon: <FolderOutlined />, label: '模型管理', description: '本地模型' },
  { key: '/modelhub', icon: <CloudOutlined />, label: '模型中心', description: '下载模型' },
  { key: '/datasets', icon: <DatabaseOutlined />, label: '数据集', description: '训练数据' },
  { key: '/training', icon: <PlayCircleOutlined />, label: '模型训练', description: '微调任务' },
  { key: '/chat', icon: <MessageOutlined />, label: 'AI 对话', description: '智能助手' },
  { key: '/knowledge', icon: <BookOutlined />, label: '知识库', description: 'RAG检索' },
  { key: '/memory', icon: <BulbOutlined />, label: '智能记忆', description: '三级记忆系统' },
  { key: '/workspace', icon: <AppstoreOutlined />, label: '工作空间', description: '项目管理' },
  { key: '/skills', icon: <ToolOutlined />, label: '技能管理', description: '技能执行' },
  { key: '/inference', icon: <ThunderboltOutlined />, label: '推理测试', description: '模型测试' },
  { key: '/history', icon: <HistoryOutlined />, label: '训练历史', description: '任务记录' },
  { key: '/project-context', icon: <CodeOutlined />, label: '项目上下文', description: '代码理解' },
  { key: '/cloud-api', icon: <CloudOutlined />, label: '云端 API', description: 'API Key 管理' },
  { key: '/cua-control', icon: <DesktopOutlined />, label: 'CUA 控制', description: '控制面板' },
  { key: '/cua-recorder', icon: <PlayCircleOutlined />, label: '操作录制', description: '录制回放' },
  { key: '/cua-memory', icon: <BulbOutlined />, label: '记忆配置', description: '技能记忆' },
  { key: '/mcp', icon: <ApiOutlined />, label: 'MCP 工具', description: '工具集成' },
  { key: '/gateway', icon: <ClusterOutlined />, label: 'Gateway', description: '设备管理' },
  { key: '/heartbeat', icon: <HeartOutlined />, label: 'Heartbeat', description: '任务调度' },
  { key: '/feedback', icon: <LikeOutlined />, label: '用户反馈', description: '反馈管理' },
  { key: '/help', icon: <QuestionCircleOutlined />, label: '帮助中心', description: '使用指南' },
]

// 动画配置
const menuItemVariants = {
  hidden: { opacity: 0, x: -10 },
  show: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: {
      delay: i * 0.03,
      duration: 0.2,
      ease: [0.16, 1, 0.3, 1] as const
    }
  })
}

const logoVariants = {
  hidden: { opacity: 0, y: -10 },
  show: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.3,
      ease: [0.16, 1, 0.3, 1] as const
    }
  }
}

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { sidebarCollapsed, toggleSidebar, backendStatus } = useAppStore()
  const [, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const handleMenuClick = (key: string) => {
    navigate(key)
  }

  return (
    <Sider
      width={sidebarCollapsed ? 72 : 240}
      collapsible={false}
      collapsed={sidebarCollapsed}
      className="sidebar-container"
      style={{
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border-color)',
        position: 'fixed',
        left: 0,
        top: 0,
        bottom: 0,
        zIndex: 100,
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Logo区域 */}
      <motion.div
        variants={logoVariants}
        initial="hidden"
        animate="show"
        style={{
          padding: sidebarCollapsed ? '20px 16px' : '24px 20px',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
          gap: '12px',
        }}
      >
        <motion.div
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          style={{
            width: 36,
            height: 36,
            borderRadius: '8px',
            background: '#2d2d2d',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '18px',
            color: '#fff',
            flexShrink: 0,
            cursor: 'pointer',
          }}
          onClick={() => navigate('/dashboard')}
        >
          <ThunderboltOutlined />
        </motion.div>
        {!sidebarCollapsed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <h2 style={{
              margin: 0,
              fontSize: '16px',
              fontWeight: 600,
              color: 'var(--text-primary)',
              whiteSpace: 'nowrap',
            }}>
              Finetune
            </h2>
            <p style={{
              margin: '2px 0 0',
              color: 'var(--text-tertiary)',
              fontSize: '11px',
              whiteSpace: 'nowrap',
              letterSpacing: '0.5px',
            }}>
              AI 微调平台
            </p>
          </motion.div>
        )}
      </motion.div>

      {/* 后端状态指示器 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        <Tooltip
          title={backendStatus === 'connected' ? '后端服务正常运行' : '后端服务未连接'}
          placement="right"
        >
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            fontSize: 12,
            color: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)',
            cursor: 'pointer',
            justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
            padding: '6px 10px',
            borderRadius: '6px',
            background: backendStatus === 'connected' ? 'var(--success-light)' : 'var(--error-light)',
            transition: 'all 0.2s ease',
          }}>
            <span style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: backendStatus === 'connected' ? 'var(--success)' : 'var(--error)',
              display: 'inline-block',
              position: 'relative',
            }}>
              {backendStatus === 'connected' && (
                <span style={{
                  position: 'absolute',
                  inset: -4,
                  borderRadius: '50%',
                  border: `2px solid ${'var(--success)'}`,
                  animation: 'pulse-ring 2s cubic-bezier(0.215, 0.61, 0.355, 1) infinite',
                }} />
              )}
            </span>
            {!sidebarCollapsed && (
              <span style={{ fontWeight: 500 }}>
                {backendStatus === 'connected' ? '服务正常' : '未连接'}
              </span>
            )}
          </div>
        </Tooltip>
      </motion.div>

      {/* 菜单区域 */}
      <div
        className="sidebar-menu-wrapper"
        style={{
          padding: '12px 8px',
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          minHeight: 0,
        }}
      >
        {menuItems.map((item, index) => (
          <Tooltip
            key={item.key}
            title={sidebarCollapsed ? item.label : undefined}
            placement="right"
          >
            <motion.div
              custom={index}
              variants={menuItemVariants}
              initial="hidden"
              animate="show"
              className={`sidebar-menu-item ${location.pathname === item.key ? 'active' : ''}`}
              onClick={() => handleMenuClick(item.key)}
              whileHover={{ x: 2 }}
              whileTap={{ scale: 0.98 }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: sidebarCollapsed ? '10px' : '10px 14px',
                margin: '3px 0',
                borderRadius: '6px',
                cursor: 'pointer',
                color: location.pathname === item.key ? 'var(--text-primary)' : 'var(--text-secondary)',
                background: location.pathname === item.key ? 'var(--bg-hover)' : 'transparent',
                transition: 'all 0.15s ease',
                position: 'relative',
                overflow: 'hidden',
                justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
              }}
            >
              {/* 激活指示器 */}
              {location.pathname === item.key && (
                <motion.span
                  layoutId="activeIndicator"
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

              <span style={{
                fontSize: 16,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'transform 0.15s ease',
                color: location.pathname === item.key ? 'var(--accent-primary)' : 'inherit',
              }}>
                {item.icon}
              </span>

              {!sidebarCollapsed && (
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{
                    fontSize: 13,
                    fontWeight: location.pathname === item.key ? 600 : 500,
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                  }}>
                    {item.label}
                  </div>
                  {item.description && (
                    <div style={{
                      fontSize: 11,
                      color: 'var(--text-tertiary)',
                      marginTop: 1,
                      whiteSpace: 'nowrap',
                    }}>
                      {item.description}
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          </Tooltip>
        ))}
      </div>

      {/* 折叠按钮 */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        onClick={toggleSidebar}
        whileHover={{ backgroundColor: 'var(--bg-hover)' }}
        whileTap={{ scale: 0.98 }}
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          padding: '16px',
          borderTop: '1px solid var(--border-color)',
          cursor: 'pointer',
          color: 'var(--text-secondary)',
          background: 'var(--bg-secondary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
          gap: 10,
          fontSize: 13,
          fontWeight: 500,
          transition: 'all 0.2s ease',
        }}
      >
        <motion.span
          animate={{ rotate: sidebarCollapsed ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ fontSize: 14 }}
        >
          {sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </motion.span>
        {!sidebarCollapsed && (
          <span>收起侧边栏</span>
        )}
      </motion.div>

      <style>{`
        .sidebar-container {
          transition: width 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .sidebar-menu-item:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }

        .sidebar-menu-item.active {
          font-weight: 600;
        }

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

        /* 滚动条样式 */
        .sidebar-menu-wrapper::-webkit-scrollbar {
          width: 4px;
        }

        .sidebar-menu-wrapper::-webkit-scrollbar-track {
          background: transparent;
        }

        .sidebar-menu-wrapper::-webkit-scrollbar-thumb {
          background: var(--border-color);
          border-radius: 2px;
        }

        .sidebar-menu-wrapper::-webkit-scrollbar-thumb:hover {
          background: var(--text-tertiary);
        }
      `}</style>
    </Sider>
  )
}
