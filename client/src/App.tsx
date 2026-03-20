import { useState, useEffect, Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Layout, message, ConfigProvider, theme as antdTheme } from 'antd'
import { AnimatePresence, motion } from 'framer-motion'

import Sidebar from './components/Sidebar'
import HeaderBar from './components/HeaderBar'
import ErrorBoundary from './components/ErrorBoundary'
import { useAppStore } from './store/appStore'
import { checkBackendHealth } from './services/api'
import { ThemeProvider, useTheme } from './theme'
import zhCN from 'antd/locale/zh_CN'

const { Content } = Layout

// 懒加载页面组件
const Dashboard = lazy(() => import('./pages/Dashboard'))
const DeviceInfo = lazy(() => import('./pages/DeviceInfo'))
const ModelManager = lazy(() => import('./pages/ModelManager'))
const DatasetManager = lazy(() => import('./pages/DatasetManager'))
const Training = lazy(() => import('./pages/Training'))
const Chat = lazy(() => import('./pages/Chat'))
const KnowledgeBase = lazy(() => import('./pages/KnowledgeBase'))
const WorkspaceManager = lazy(() => import('./pages/WorkspaceManager'))
const ModelHub = lazy(() => import('./pages/ModelHub'))
const Inference = lazy(() => import('./pages/Inference'))
const History = lazy(() => import('./pages/History'))
const ProjectContext = lazy(() => import('./pages/ProjectContext'))
const APIKeyManager = lazy(() => import('./pages/APIKeyManager'))
const Skills = lazy(() => import('./pages/Skills'))
const MemoryPage = lazy(() => import('./pages/MemoryPage'))
const CUAControl = lazy(() => import('./pages/CUAControl'))
const ActionRecorder = lazy(() => import('./pages/ActionRecorder'))
const SkillMemory = lazy(() => import('./pages/SkillMemory'))
const MCPTools = lazy(() => import('./pages/MCPTools'))
const GatewayPage = lazy(() => import('./pages/GatewayPage'))
const HeartbeatPage = lazy(() => import('./pages/HeartbeatPage'))
const FeedbackPanel = lazy(() => import('./components/FeedbackPanel'))
const HelpPanel = lazy(() => import('./components/HelpPanel'))

// 页面过渡动画配置
const pageVariants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 }
}

const pageTransition = {
  duration: 0.3,
  ease: [0.16, 1, 0.3, 1] as const
}

// 页面包装组件
function PageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial="initial"
      animate="animate"
      exit="exit"
      variants={pageVariants}
      transition={pageTransition}
      style={{ height: '100%' }}
    >
      {children}
    </motion.div>
  )
}

// 加载动画组件
const LoadingScreen = () => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100vh',
      background: 'var(--bg-primary)',
      gap: 24,
    }}
  >
    <motion.div
      animate={{ opacity: [0.8, 1, 0.8] }}
      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
      style={{
        width: 56,
        height: 56,
        borderRadius: '12px',
        background: 'var(--text-primary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '28px',
        color: 'var(--text-inverse)',
      }}
    >
      ⚡
    </motion.div>
    <div style={{ textAlign: 'center' }}>
      <div style={{
        fontSize: '18px',
        fontWeight: 600,
        color: 'var(--text-primary)',
        marginBottom: 8,
      }}>
        Finetune Platform
      </div>
      <div style={{
        fontSize: '14px',
        color: 'var(--text-secondary)',
      }}>
        正在初始化...
      </div>
    </div>
  </motion.div>
)

// 页面加载占位
const PageLoader = () => (
  <div style={{
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100%',
    minHeight: '400px',
  }}>
    <motion.div
      animate={{ rotate: 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
      style={{
        width: 32,
        height: 32,
        border: '2px solid var(--border-color)',
        borderTopColor: 'var(--accent-primary)',
        borderRadius: '50%',
      }}
    />
  </div>
)

// 路由配置
const routes = [
  { path: '/dashboard', element: <Dashboard /> },
  { path: '/device', element: <DeviceInfo /> },
  { path: '/models', element: <ModelManager /> },
  { path: '/datasets', element: <DatasetManager /> },
  { path: '/training', element: <Training /> },
  { path: '/chat', element: <Chat /> },
  { path: '/knowledge', element: <KnowledgeBase /> },
  { path: '/workspace', element: <WorkspaceManager /> },
  { path: '/skills', element: <Skills /> },
  { path: '/memory', element: <MemoryPage /> },
  { path: '/modelhub', element: <ModelHub /> },
  { path: '/inference', element: <Inference /> },
  { path: '/history', element: <History /> },
  { path: '/project-context', element: <ProjectContext /> },
  { path: '/cloud-api', element: <APIKeyManager /> },
  { path: '/cua-control', element: <CUAControl /> },
  { path: '/cua-recorder', element: <ActionRecorder /> },
  { path: '/cua-memory', element: <SkillMemory /> },
  { path: '/mcp', element: <MCPTools /> },
  { path: '/gateway', element: <GatewayPage /> },
  { path: '/heartbeat', element: <HeartbeatPage /> },
  { path: '/feedback', element: <FeedbackPanel /> },
  { path: '/help', element: <HelpPanel /> },
]

function AppContent() {
  const location = useLocation()
  const { setBackendUrl, setBackendStatus, sidebarCollapsed } = useAppStore()
  const { theme } = useTheme()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const initApp = async () => {
      try {
        if (window.electronAPI) {
          const url = await window.electronAPI.getBackendUrl()
          setBackendUrl(url)
        } else {
          setBackendUrl('http://127.0.0.1:8000')
        }

        const isHealthy = await checkBackendHealth()
        setBackendStatus(isHealthy ? 'connected' : 'disconnected')

        if (!isHealthy) {
          message.warning('后端服务未连接，请启动应用')
        }
      } catch (error) {
        console.error('Init error:', error)
        setBackendStatus('disconnected')
      } finally {
        setLoading(false)
      }
    }

    initApp()

    const checkInterval = setInterval(async () => {
      try {
        const isHealthy = await checkBackendHealth()
        setBackendStatus(isHealthy ? 'connected' : 'disconnected')
      } catch (error) {
        setBackendStatus('disconnected')
      }
    }, 5000)

    return () => clearInterval(checkInterval)
  }, [])

  if (loading) {
    return <LoadingScreen />
  }

  return (
    <ErrorBoundary>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: theme === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
          token: {
            colorPrimary: '#d4a373',
            colorSuccess: '#5b8a72',
            colorWarning: '#d4a373',
            colorError: '#c45c48',
            colorInfo: '#5b8a72',
            borderRadius: 6,
            borderRadiusLG: 8,
            borderRadiusSM: 4,
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            fontSize: 14,
            fontSizeLG: 16,
            fontSizeSM: 12,
            controlHeight: 36,
            controlHeightLG: 44,
            controlHeightSM: 28,
          },
          components: {
            Button: {
              borderRadius: 6,
              controlHeight: 36,
            },
            Card: {
              borderRadius: 8,
            },
            Input: {
              borderRadius: 6,
            },
            Select: {
              borderRadius: 6,
            },
            Modal: {
              borderRadius: 12,
            },
            Tooltip: {
              borderRadius: 6,
            },
          }
        }}
      >
        <Layout
          style={{
            minHeight: '100vh',
            background: 'var(--bg-primary)',
          }}
        >
          <Sidebar />
          <Layout
            style={{
              marginLeft: sidebarCollapsed ? 72 : 240,
              transition: 'margin-left 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
              minHeight: '100vh',
            }}
          >
            <HeaderBar />
            <Content
              style={{
                margin: '20px 16px',
                padding: 0,
                minHeight: 'calc(100vh - 64px - 40px)',
              }}
            >
              <AnimatePresence mode="wait">
                <Routes location={location} key={location.pathname}>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  {routes.map(({ path, element }) => (
                    <Route
                      key={path}
                      path={path}
                      element={
                        <PageWrapper>
                          <Suspense fallback={<PageLoader />}>
                            {element}
                          </Suspense>
                        </PageWrapper>
                      }
                    />
                  ))}
                </Routes>
              </AnimatePresence>
            </Content>
          </Layout>
        </Layout>
      </ConfigProvider>
    </ErrorBoundary>
  )
}

function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  )
}

export default App
