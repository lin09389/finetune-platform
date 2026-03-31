import { useState, useEffect, useRef, Suspense, lazy } from 'react'
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
const Chat = lazy(() => import('./pages/ChatNew'))
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

// 椤甸潰杩囨浮鍔ㄧ敾閰嶇疆
const pageVariants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 }
}

const pageTransition = {
  duration: 0.3,
  ease: [0.16, 1, 0.3, 1] as const
}

// 椤甸潰鍖呰缁勪欢
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

// 鍔犺浇鍔ㄧ敾缁勪欢
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
      鈿?    </motion.div>
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
        姝ｅ湪鍒濆鍖?..
      </div>
    </div>
  </motion.div>
)

// 椤甸潰鍔犺浇鍗犱綅
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

// 璺敱閰嶇疆
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
  const disconnectWarnedRef = useRef(false)
  useEffect(() => {
    const applyBackendStatus = (isHealthy: boolean) => {
      setBackendStatus(isHealthy ? 'connected' : 'disconnected')

      if (isHealthy) {
        disconnectWarnedRef.current = false
        return
      }

      if (!disconnectWarnedRef.current) {
        message.warning('后端服务未连接，请启动应用')
        disconnectWarnedRef.current = true
      }
    }

    const initApp = async () => {
      try {
        if (window.electronAPI) {
          const url = await window.electronAPI.getBackendUrl()
          setBackendUrl(url)
        } else {
          setBackendUrl('http://127.0.0.1:8000')
        }

        const isHealthy = await checkBackendHealth()
        applyBackendStatus(isHealthy)
      } catch (error) {
        console.error('Init error:', error)
        applyBackendStatus(false)
      } finally {
        setLoading(false)
      }
    }

    initApp()

    const checkInterval = setInterval(async () => {
      try {
        const isHealthy = await checkBackendHealth()
        applyBackendStatus(isHealthy)
      } catch (error) {
        applyBackendStatus(false)
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
            borderRadius: 8,
            borderRadiusLG: 12,
            borderRadiusSM: 4,
            fontFamily: "'Inter', 'Source Han Sans CN', -apple-system, BlinkMacSystemFont, sans-serif",
            fontSize: 15,
            fontSizeLG: 18,
            fontSizeSM: 13,
            controlHeight: 40,
            controlHeightLG: 48,
            controlHeightSM: 32,
            boxShadow: 'var(--shadow-md)',
          },
          components: {
            Button: {
              borderRadius: 8,
              controlHeight: 40,
              fontWeight: 600,
            },
            Card: {
              borderRadius: 12,
              boxShadow: 'var(--shadow-sm)',
            },
            Input: {
              borderRadius: 8,
              controlHeight: 40,
            },
            Select: {
              borderRadius: 8,
              controlHeight: 40,
            },
            Modal: {
              borderRadius: 16,
              boxShadow: 'var(--shadow-xl)',
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
              transition: 'margin-left 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
              minHeight: '100vh',
              background: 'transparent',
            }}
          >
            <HeaderBar />
            <Content
              style={{
                margin: 'clamp(16px, 2vw, 32px) clamp(12px, 2vw, 24px)',
                padding: 0,
                minHeight: 'calc(100vh - 64px - 64px)',
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

