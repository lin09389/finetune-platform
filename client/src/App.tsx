import { App as AntApp, ConfigProvider, Layout, Result, theme as antdTheme } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import zhCN from 'antd/locale/zh_CN';
import ErrorBoundary from './components/ErrorBoundary';
import HeaderBar from './components/HeaderBar';
import MobileNav, { MobileBottomNav } from './components/MobileNav';
import PageSkeleton from './components/shared/PageSkeleton';
import Sidebar from './components/Sidebar';
import { PageTransition } from './components/motion';
import { useResponsive } from './hooks/useResponsive';
import { RuntimeContextProvider } from './runtime/RuntimeContext';
import { API_BASE_URL, checkBackendHealth, startHealthCheck } from './services/api';
import { useAppStore } from './store/appStore';
import { useShallow } from 'zustand/react/shallow';
import { ThemeProvider, useTheme } from './theme';
import ContextualToolbar from './components/shared/ContextualToolbar';
import TechBackground from './components/shared/TechBackground';
import ExperimentalRouteGuard from './capability/ExperimentalRouteGuard';
import { setModalAdapter } from './utils/modal';
import { setNotifyAdapter } from './utils/notify';
import { getRouteTitle } from './routes/meta';

const { Content } = Layout;

const Dashboard = lazy(() => import('./pages/Dashboard'));
const DeviceInfo = lazy(() => import('./pages/DeviceInfo'));
const ModelRuntimeCenter = lazy(() => import('./pages/ModelRuntimeCenter'));
const DatasetManager = lazy(() => import('./pages/DatasetManager'));
const Training = lazy(() => import('./pages/Training'));
const Chat = lazy(() => import('./pages/ChatNew'));
const AgentWorkbench = lazy(() => import('./agent/workbench/AgentWorkbenchRoute'));
const KnowledgeBase = lazy(() => import('./pages/KnowledgeBase'));
const WorkspaceManager = lazy(() => import('./pages/WorkspaceManager'));
const Inference = lazy(() => import('./pages/Inference'));
const Evaluation = lazy(() => import('./pages/Evaluation'));
const Deployment = lazy(() => import('./pages/Deployment'));
const History = lazy(() => import('./pages/History'));
const ProjectContext = lazy(() => import('./pages/ProjectContext'));
const APIKeyManager = lazy(() => import('./pages/APIKeyManager'));
const MemoryPage = lazy(() => import('./pages/MemoryPage'));

const CUAControl = lazy(() => import('./pages/CUAControl'));
const ActionRecorder = lazy(() => import('./pages/ActionRecorder'));
const MCPTools = lazy(() => import('./pages/MCPTools'));
const GatewayPage = lazy(() => import('./pages/GatewayPage'));
const HeartbeatPage = lazy(() => import('./pages/HeartbeatPage'));
const DesignSystem = lazy(() => import('./pages/DesignSystem'));
const SharedChat = lazy(() => import('./pages/SharedChat'));
const FeedbackPanel = lazy(() => import('./components/FeedbackPanel'));
const HelpPanel = lazy(() => import('./components/HelpPanel'));

function PageWrapper({ children, locationKey }: { children: React.ReactNode; locationKey: string }) {
  return (
    <PageTransition locationKey={locationKey} style={{ height: '100%' }}>
      {children}
    </PageTransition>
  );
}

const LoadingScreen = () => (
  <motion.div
    role="status"
    aria-live="polite"
    aria-label="正在加载 Finetune Platform"
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
        background: 'var(--accent-primary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '24px',
        fontWeight: 800,
        color: 'var(--text-inverse)',
        boxShadow: 'var(--shadow-sm)',
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
);

const PageLoader = () => (
  <div style={{ minHeight: '400px' }}>
    <PageSkeleton />
  </div>
);

const NotFound = () => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
    <Result
      status="404"
      title="404"
      subTitle="抱歉，你访问的页面不存在。"
      extra={<Link to="/agent">返回工作台</Link>}
    />
  </div>
);

const routes = [
  { path: '/dashboard', element: <Dashboard /> },
  { path: '/device', element: <DeviceInfo /> },
  { path: '/models', element: <ModelRuntimeCenter /> },
  { path: '/datasets', element: <DatasetManager /> },
  { path: '/training', element: <Training /> },
  { path: '/chat', element: <Chat /> },
  { path: '/agent', element: <AgentWorkbench /> },
  { path: '/knowledge', element: <KnowledgeBase /> },
  { path: '/workspace', element: <WorkspaceManager /> },
  { path: '/memory', element: <MemoryPage /> },
  // Legacy alias: old /modelhub bookmarked URLs redirect to unified center
  { path: '/modelhub', element: <Navigate to="/models" replace /> },
  { path: '/inference', element: <Inference /> },
  { path: '/evaluation', element: <Evaluation /> },
  { path: '/deployment', element: <Deployment /> },
  { path: '/history', element: <History /> },
  { path: '/training-compare', element: <History mode="compare" /> },
  { path: '/project-context', element: <ProjectContext /> },
  { path: '/cloud-api', element: <APIKeyManager /> },
  { path: '/cua-control', element: <CUAControl /> },
  { path: '/cua-recorder', element: <ActionRecorder /> },
  { path: '/mcp', element: <MCPTools /> },
  { path: '/gateway', element: <GatewayPage /> },
  { path: '/heartbeat', element: <HeartbeatPage /> },
  { path: '/design-system', element: <DesignSystem /> },
  { path: '/share/:shareId', element: <SharedChat /> },
  { path: '/feedback', element: <FeedbackPanel /> },
  { path: '/help', element: <HelpPanel /> },
];

function AppContent() {
  const { message, modal } = AntApp.useApp();
  const location = useLocation();
  const isChatRoute = location.pathname === '/chat';
  const isAgentWorkbenchRoute = location.pathname === '/agent';
  const isImmersiveRoute = isChatRoute || isAgentWorkbenchRoute;
  const { setBackendUrl, setBackendStatus, sidebarCollapsed } = useAppStore(useShallow(state => ({
    setBackendUrl: state.setBackendUrl,
    setBackendStatus: state.setBackendStatus,
    sidebarCollapsed: state.sidebarCollapsed
  })));
  const { theme } = useTheme();
  const { isMobile, isTablet } = useResponsive();
  const useCompactNav = isMobile || isTablet;
  const [loading, setLoading] = useState(true);
  const disconnectWarnedRef = useRef(false);

  useEffect(() => {
    const title = getRouteTitle(location.pathname);
    document.title = `${title} · Finetune Platform`;
  }, [location.pathname]);

  // Move focus to the main content region on route change so keyboard and
  // screen-reader users land on the new page content instead of staying on the
  // previous element (SPA navigation does not move focus by default).
  useEffect(() => {
    const el = document.getElementById('main-content');
    el?.focus();
  }, [location.pathname]);

  useEffect(() => {
    setNotifyAdapter({
      success: (content) => message.success(content),
      warning: (content) => message.warning(content),
      error: (content) => message.error(content),
      info: (content) => message.info(content),
    });
    setModalAdapter({
      confirm: (config) => modal.confirm(config),
      success: (config) => modal.success(config),
    });

    return () => {
      setNotifyAdapter(null);
      setModalAdapter(null);
    };
  }, [message, modal]);

  useEffect(() => {
    const applyBackendStatus = (isHealthy: boolean) => {
      setBackendStatus(isHealthy ? 'connected' : 'disconnected');

      if (isHealthy) {
        disconnectWarnedRef.current = false;
        return;
      }

      if (!disconnectWarnedRef.current) {
        message.warning('后端服务未连接，请先启动后端');
        disconnectWarnedRef.current = true;
      }
    };

    const initApp = async () => {
      try {
        if (window.electronAPI) {
          const url = await window.electronAPI.getBackendUrl();
          setBackendUrl(url);
        } else {
          setBackendUrl(API_BASE_URL);
        }

        const isHealthy = await checkBackendHealth();
        applyBackendStatus(isHealthy);
      } catch {
        applyBackendStatus(false);
      } finally {
        setLoading(false);
      }
    };

    void initApp();

    // 启用混合健康状态监听（首选 WS，降级 HTTP 轮询）
    const cleanupHealthCheck = startHealthCheck((isHealthy) => {
      applyBackendStatus(isHealthy);
    });

    return () => {
      cleanupHealthCheck();
    };
  }, [message, setBackendStatus, setBackendUrl]);

  // Memoize the antd theme config: it only changes when the color mode changes.
  // Without this, AppContent re-renders (e.g. on backend status / location
  // changes) recreate the object and force antd to reprocess the whole theme.
  const antdThemeConfig = useMemo(
    () => ({
      // Emit antd design tokens as CSS variables (e.g. --ant-color-primary) so
      // they can be overridden from variables.css, and theme switches no longer
      // require regenerating antd's CSS. hashed:false drops the class-name hash
      // suffix (smaller CSS, easier debugging).
      cssVar: true,
      hashed: false,
      algorithm: theme === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token: {
        colorPrimary: theme === 'dark' ? '#D97757' : '#b35433',
        colorSuccess: theme === 'dark' ? '#8ca06f' : '#65754e',
        colorWarning: theme === 'dark' ? '#D4A033' : '#916909',
        colorError: theme === 'dark' ? '#ef4444' : '#d64545',
        colorInfo: theme === 'dark' ? '#7B9BB8' : '#5B7B9A',
        colorBgBase: theme === 'dark' ? '#262624' : '#faf9f5',
        colorBgContainer: theme === 'dark' ? '#2c2c2b' : '#f5f4ef',
        colorBgElevated: theme === 'dark' ? '#30302e' : '#ede9de',
        colorBorder: theme === 'dark' ? '#3e3e38' : '#dad9d4',
        colorText: theme === 'dark' ? '#f1f1ef' : '#3d3929',
        colorTextSecondary: theme === 'dark' ? '#b7b5a9' : '#6e6d68',
        colorTextTertiary: theme === 'dark' ? '#908e84' : '#9b988c',
        colorTextQuaternary: theme === 'dark' ? '#6e6d68' : '#c2c0b6',
        colorBgLayout: 'transparent',
        colorBorderSecondary: theme === 'dark' ? '#30302e' : '#ede9de',
        // Claude radius: base 12, LG 16, SM 8 — editorial soft geometry
        borderRadius: 12,
        borderRadiusLG: 16,
        borderRadiusSM: 8,
        borderRadiusXS: 4,
        // Claude typography: Poppins for compact UI, full fallback stack
        fontFamily:
          "'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
        fontFamilyCode: "'Geist Mono', ui-monospace, 'SFMono-Regular', 'Consolas', monospace",
        fontSize: 14,
        fontSizeLG: 16,
        fontSizeSM: 13,
        fontSizeXL: 18,
        fontSizeHeading1: 32,
        fontSizeHeading2: 26,
        fontSizeHeading3: 22,
        fontSizeHeading4: 18,
        fontSizeHeading5: 16,
        lineHeight: 1.5,
        lineHeightHeading1: 1.25,
        lineHeightHeading2: 1.3,
        lineHeightHeading3: 1.375,
        controlHeight: 40,
        controlHeightLG: 46,
        controlHeightSM: 32,
        controlHeightXS: 24,
        // Claude shadows — premium layered warm-tinted depth
        boxShadow: '0 1px 3px 0px rgba(61, 57, 41, 0.08), 0 1px 2px -1px rgba(61, 57, 41, 0.06)',
        boxShadowSecondary: '0 4px 6px -1px rgba(61, 57, 41, 0.08), 0 2px 4px -2px rgba(61, 57, 41, 0.06)',
        boxShadowTertiary: '0 1px 3px 0px rgba(61, 57, 41, 0.06)',
        // Claude motion — 0.16s ease
        motionDurationFast: '0.1s',
        motionDurationMid: '0.16s',
        motionDurationSlow: '0.24s',
        motionEaseInOut: 'cubic-bezier(0.16, 1, 0.3, 1)',
        motionEaseOut: 'cubic-bezier(0.16, 1, 0.3, 1)',
        motionEaseIn: 'cubic-bezier(0.75, 0, 0.25, 1)',
        wireframe: false,
      },
      components: {
        Button: {
          borderRadius: 12,
          borderRadiusLG: 16,
          borderRadiusSM: 8,
          controlHeight: 40,
          controlHeightLG: 46,
          controlHeightSM: 32,
          fontWeight: 500,
          primaryShadow: '0 1px 3px 0px rgba(0, 0, 0, 0.05)',
          defaultShadow: '0 1px 3px 0px rgba(0, 0, 0, 0.05)',
          paddingInline: 18,
          paddingInlineSM: 12,
          paddingInlineLG: 22,
        },
        Card: {
          borderRadius: 16,
          borderRadiusLG: 20,
          boxShadow: 'none',
          boxShadowTertiary: '0 1px 3px 0px rgba(0, 0, 0, 0.05)',
          colorBgContainer: 'transparent',
          paddingLG: 24,
          paddingMD: 20,
          paddingSM: 16,
        },
        Input: {
          borderRadius: 12,
          borderRadiusLG: 16,
          borderRadiusSM: 8,
          controlHeight: 40,
          controlHeightLG: 46,
          controlHeightSM: 32,
          paddingInline: 16,
          colorBgContainer: theme === 'dark' ? '#30302e' : '#ffffff',
        },
        InputNumber: {
          borderRadius: 12,
          controlHeight: 40,
          controlHeightLG: 46,
          controlHeightSM: 32,
        },
        Select: {
          borderRadius: 12,
          borderRadiusLG: 16,
          controlHeight: 40,
          controlHeightLG: 46,
          controlHeightSM: 32,
          colorBgContainer: theme === 'dark' ? '#30302e' : '#ffffff',
        },
        Modal: {
          borderRadius: 20,
          borderRadiusLG: 24,
          boxShadow: '0 20px 25px -5px rgba(61, 57, 41, 0.10), 0 8px 10px -6px rgba(61, 57, 41, 0.08)',
          contentBg: theme === 'dark' ? '#2c2c2b' : '#f5f4ef',
          headerBg: 'transparent',
          titleFontSize: 22,
          titleColor: theme === 'dark' ? '#f1f1ef' : '#3d3929',
        },
        Drawer: {
          borderRadiusLG: 20,
        },
        Tooltip: {
          borderRadius: 8,
          fontSize: 12,
        },
        Menu: {
          borderRadius: 10,
          itemHeight: 38,
          itemPaddingInline: 12,
          iconSize: 16,
          activeBarBorderWidth: 0,
        },
        Tag: {
          borderRadius: 6,
          fontSize: 12,
        },
        Table: {
          borderRadius: 16,
          headerBg: theme === 'dark' ? '#30302e' : '#ede9de',
          headerColor: theme === 'dark' ? '#f1f1ef' : '#3d3929',
          rowHoverBg: theme === 'dark' ? '#3e3e38' : '#f5f4ef',
          borderColor: theme === 'dark' ? '#3e3e38' : '#dad9d4',
          cellPaddingBlock: 14,
          cellPaddingInline: 16,
        },
        Tabs: {
          itemColor: theme === 'dark' ? '#b7b5a9' : '#6e6d68',
          itemSelectedColor: theme === 'dark' ? '#f1f1ef' : '#3d3929',
          itemHoverColor: theme === 'dark' ? '#f1f1ef' : '#3d3929',
          inkBarColor: theme === 'dark' ? '#d97757' : '#b35433',
          horizontalItemPadding: '12px 16px',
          horizontalMargin: '0 0 16px 0',
        },
        Segmented: {
          borderRadius: 10,
          itemSelectedBg: theme === 'dark' ? '#30302e' : '#ffffff',
          itemSelectedColor: theme === 'dark' ? '#f1f1ef' : '#3d3929',
        },
        Progress: {
          defaultColor: theme === 'dark' ? '#d97757' : '#b35433',
          borderRadius: 999,
        },
        Switch: {
          colorPrimary: theme === 'dark' ? '#d97757' : '#b35433',
          colorPrimaryHover: theme === 'dark' ? '#e08d6f' : '#b0562f',
        },
        Slider: {
          colorPrimary: theme === 'dark' ? '#d97757' : '#b35433',
          colorPrimaryBorder: theme === 'dark' ? '#8a5740' : '#e0a892',
          handleSize: 10,
          handleSizeHover: 12,
        },
        Checkbox: {
          colorPrimary: theme === 'dark' ? '#d97757' : '#b35433',
          colorPrimaryHover: theme === 'dark' ? '#e08d6f' : '#b0562f',
          borderRadius: 4,
        },
        Radio: {
          colorPrimary: theme === 'dark' ? '#d97757' : '#b35433',
          colorPrimaryHover: theme === 'dark' ? '#e08d6f' : '#b0562f',
          buttonSolidCheckedBg: theme === 'dark' ? '#d97757' : '#b35433',
          buttonSolidCheckedColor: theme === 'dark' ? '#141413' : '#ffffff',
        },
        Pagination: {
          colorPrimary: theme === 'dark' ? '#d97757' : '#b35433',
          itemBg: 'transparent',
          itemSize: 36,
        },
        DatePicker: {
          borderRadius: 12,
          controlHeight: 40,
        },
        Empty: {
          colorTextDescription: theme === 'dark' ? '#908e84' : '#9b988c',
        },
        Statistic: {
          contentFontSize: 28,
        },
        Layout: {
          bodyBg: 'transparent',
          headerBg: 'transparent',
          siderBg: 'transparent',
        },
      },
    }),
    [theme],
  );

  if (loading) {
    return <LoadingScreen />;
  }

  return (
    <ErrorBoundary>
      <ConfigProvider
        locale={zhCN}
        theme={antdThemeConfig}
      >
        <TechBackground />
        <ContextualToolbar />
        <a href="#main-content" className="skip-link">
          跳到主内容
        </a>
        <Layout
          className="app-shell"
          style={{
            minHeight: '100vh',
            background: 'transparent',
          }}
        >
          {!useCompactNav && !isAgentWorkbenchRoute && <Sidebar />}
          {!isAgentWorkbenchRoute && <MobileNav />}
          <Layout
            className="app-main"
            style={{
              marginLeft: isAgentWorkbenchRoute ? 0 : useCompactNav ? 0 : sidebarCollapsed ? 104 : 272,
              transition: 'margin-left 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
              minHeight: '100vh',
              background: 'transparent',
            }}
          >
            {!isImmersiveRoute && <HeaderBar />}
            <Content
              id="main-content"
              role="main"
              aria-label="主内容"
              className="app-content"
              tabIndex={-1}
              style={{
                margin: isImmersiveRoute
                  ? 0
                  : isMobile
                    ? '12px 10px 76px'
                    : useCompactNav
                      ? '16px 14px 84px'
                      : '16px 24px 24px 24px',
                padding: 0,
                height: isImmersiveRoute ? '100vh' : undefined,
                minHeight: isImmersiveRoute ? '100vh' : 'calc(100vh - 56px - 40px)',
                borderRadius: isImmersiveRoute ? 0 : '16px', // Rounded corners for content area
                overflow: 'hidden', // Contain content
              }}
            >
              <AnimatePresence mode="wait">
                <Routes location={location} key={location.pathname}>
                  <Route path="/" element={<Navigate to="/agent" replace />} />
                  {routes.map(({ path, element }) => (
                    <Route
                      key={path}
                      path={path}
                      element={
                        <PageWrapper locationKey={location.pathname}>
                          <Suspense fallback={<PageLoader />}>
                            <ExperimentalRouteGuard path={path}>{element}</ExperimentalRouteGuard>
                          </Suspense>
                        </PageWrapper>
                      }
                    />
                  ))}
                  <Route
                    path="*"
                    element={
                      <PageWrapper locationKey="not-found">
                        <NotFound />
                      </PageWrapper>
                    }
                  />
                </Routes>
              </AnimatePresence>
            </Content>
            {!isAgentWorkbenchRoute && <MobileBottomNav />}
          </Layout>
        </Layout>
      </ConfigProvider>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <ThemeProvider>
      <RuntimeContextProvider>
        <AppContent />
      </RuntimeContextProvider>
    </ThemeProvider>
  );
}

export default App;
