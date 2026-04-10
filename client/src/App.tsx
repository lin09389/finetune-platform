import { useState, useEffect, useRef, Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Layout, App as AntApp, ConfigProvider, theme as antdTheme } from 'antd'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'

import Sidebar from './components/Sidebar'
import HeaderBar from './components/HeaderBar'
import ErrorBoundary from './components/ErrorBoundary'
import { useAppStore } from './store/appStore'
import { API_BASE_URL, checkBackendHealth } from './services/api'
import { ThemeProvider, useTheme } from './theme'
import { useResponsive } from './hooks/useResponsive'
import PageSkeleton from './components/shared/PageSkeleton'
import zhCN from 'antd/locale/zh_CN'

const { Content } = Layout

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
const DesignSystem = lazy(() => import('./pages/DesignSystem'))
const SharedChat = lazy(() => import('./pages/SharedChat'))
const FeedbackPanel = lazy(() => import('./components/FeedbackPanel'))
const HelpPanel = lazy(() => import('./components/HelpPanel'))

const pageVariants = {
  initial: { opacity: 0, y: 16, scale: 0.995, filter: 'blur(3px)' },
  animate: { opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' },
  exit: { opacity: 0, y: -12, scale: 0.996, filter: 'blur(2px)' },
}

const pageTransition = {
  duration: 0.38,
  ease: [0.16, 1, 0.3, 1] as const,
}

function PageWrapper({ children }: { children: React.ReactNode }) {
  const shouldReduceMotion = useReducedMotion()

  if (shouldReduceMotion) {
    return <div style={{ height: '100%' }}>{children}</div>
  }

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
      transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
      style={{
        width: 64,
        height: 64,
        borderRadius: '16px',
        background: 'var(--text-primary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '24px',
        fontWeight: 800,
        color: 'var(--bg-primary)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      FT
    </motion.div>
    <div style={{ textAlign: 'center' }}>
      <div
        style={{
          fontSize: '20px',
          fontWeight: 700,
          color: 'var(--text-primary)',
          marginBottom: 8,
          letterSpacing: '0.02em',
        }}
      >
        Finetune Platform
      </div>
      <div
        style={{
          fontSize: '14px',
          color: 'var(--text-secondary)',
        }}
      >
        正在加载工作台...
      </div>
    </div>
  </motion.div>
)

const PageLoader = () => (
  <div style={{ minHeight: '400px' }}>
    <PageSkeleton />
  </div>
)

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
  { path: '/design-system', element: <DesignSystem /> },
  { path: '/share/:shareId', element: <SharedChat /> },
  { path: '/feedback', element: <FeedbackPanel /> },
  { path: '/help', element: <HelpPanel /> },
]

function AppContent() {
  const { message } = AntApp.useApp()
  const location = useLocation()
  const { setBackendUrl, setBackendStatus, sidebarCollapsed } = useAppStore()
  const { theme } = useTheme()
  const { isMobile } = useResponsive()
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
        message.warning('后端服务未连接，请先启动后端')
        disconnectWarnedRef.current = true
      }
    }

    const initApp = async () => {
      try {
        if (window.electronAPI) {
          const url = await window.electronAPI.getBackendUrl()
          setBackendUrl(url)
        } else {
          setBackendUrl(API_BASE_URL)
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

    void initApp()

    const checkInterval = setInterval(async () => {
      try {
        const isHealthy = await checkBackendHealth()
        applyBackendStatus(isHealthy)
      } catch {
        applyBackendStatus(false)
      }
    }, 5000)

    return () => clearInterval(checkInterval)
  }, [message, setBackendStatus, setBackendUrl])

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
            colorPrimary: theme === 'dark' ? '#ffffff' : '#000000',
            colorSuccess: theme === 'dark' ? '#ededed' : '#111111',
            colorWarning: theme === 'dark' ? '#cccccc' : '#333333',
            colorError: theme === 'dark' ? '#a1a1aa' : '#111111',
            colorInfo: theme === 'dark' ? '#ffffff' : '#000000',
            colorBgBase: theme === 'dark' ? '#000000' : '#ffffff',
            colorBgContainer: theme === 'dark' ? '#0a0a0a' : '#fcfcfc',
            colorBgElevated: theme === 'dark' ? '#141414' : '#f5f5f5',
            colorBorder: theme === 'dark' ? '#27272a' : '#ebebeb',
            colorText: theme === 'dark' ? '#ffffff' : '#000000',
            colorTextSecondary: theme === 'dark' ? '#a1a1aa' : '#666666',
            borderRadius: 6,
            borderRadiusLG: 12,
            borderRadiusSM: 4,
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
            fontSize: 14,
            fontSizeLG: 16,
            fontSizeSM: 12,
            controlHeight: 36,
            controlHeightLG: 44,
            controlHeightSM: 28,
            boxShadow: 'var(--shadow-md)',
          },
          components: {
            Button: {
              borderRadius: 6,
              controlHeight: 36,
              fontWeight: 500,
            },
            Card: {
              borderRadius: 12,
              boxShadow: 'none',
            },
            Input: {
              borderRadius: 6,
              controlHeight: 36,
            },
            Select: {
              borderRadius: 6,
              controlHeight: 36,
            },
            Modal: {
              borderRadius: 16,
              boxShadow: 'var(--shadow-xl)',
            },
            Tooltip: {
              borderRadius: 6,
            },
          },
        }}
      >
        <Layout
          className="app-shell"
          style={{
            minHeight: '100vh',
            background: 'transparent',
          }}
        >
          <Sidebar />
          <Layout
            className="app-main"
            style={{
              marginLeft: isMobile ? 0 : sidebarCollapsed ? 72 : 240,
              transition: 'margin-left 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
              minHeight: '100vh',
              background: 'transparent',
            }}
          >
            <HeaderBar />
            <Content
              className="app-content"
              style={{
                margin: isMobile ? '12px 10px 20px' : 'clamp(16px, 2vw, 32px) clamp(12px, 2vw, 24px)',
                padding: 0,
                minHeight: 'calc(100vh - 56px - 32px)',
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
                          <Suspense fallback={<PageLoader />}>{element}</Suspense>
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
