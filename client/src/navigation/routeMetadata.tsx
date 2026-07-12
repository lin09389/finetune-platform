import {
  ApiOutlined,
  AppstoreOutlined,
  BookOutlined,
  BulbOutlined,
  CloudOutlined,
  ClusterOutlined,
  CodeOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  FileSearchOutlined,
  FolderOutlined,
  HeartOutlined,
  HistoryOutlined,
  LikeOutlined,
  LineChartOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';
import { ROUTE_CAPABILITY, type CapabilityTier } from '../capability/tiers';

export type NavigationSurface = 'sidebar' | 'mobile' | 'bottom';
export type NavigationGroupId = 'workbench' | 'core' | 'beta' | 'experimental' | 'support';

export interface RouteMetadata {
  path: string;
  label: string;
  mobileLabel?: string;
  description?: string;
  icon?: ReactNode;
  groups?: NavigationGroupId[];
  surfaces?: NavigationSurface[];
}

export interface NavigationGroup {
  id: NavigationGroupId;
  label: string;
  surfaces: Exclude<NavigationSurface, 'bottom'>[];
}

const routeMetadata: RouteMetadata[] = [
  {
    path: '/agent',
    label: 'Agent 工作台',
    mobileLabel: '工作台',
    description: '日常编码任务',
    icon: <RobotOutlined />,
    groups: ['workbench'],
    surfaces: ['sidebar', 'mobile', 'bottom'],
  },
  {
    path: '/chat',
    label: 'AI 对话',
    description: '轻量对话',
    icon: <MessageOutlined />,
    groups: ['workbench'],
    surfaces: ['sidebar', 'mobile', 'bottom'],
  },
  {
    path: '/dashboard',
    label: '仪表盘',
    mobileLabel: '首页',
    description: '系统概览',
    icon: <DashboardOutlined />,
    groups: ['core'],
    surfaces: ['sidebar', 'mobile', 'bottom'],
  },
  { path: '/device', label: '设备信息', description: 'GPU / CPU 状态', icon: <DesktopOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  { path: '/models', label: '模型运行', description: '接入与 Agent', icon: <FolderOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  { path: '/modelhub', label: '模型运行', groups: [], surfaces: [] },
  { path: '/datasets', label: '数据集', description: '训练数据', icon: <DatabaseOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  {
    path: '/training',
    label: '模型训练',
    description: '专业微调任务',
    icon: <PlayCircleOutlined />,
    groups: ['core'],
    surfaces: ['sidebar', 'mobile', 'bottom'],
  },
  { path: '/history', label: '训练历史', description: '任务记录', icon: <HistoryOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  { path: '/training-compare', label: '训练对比', description: '指标横评', icon: <LineChartOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  { path: '/inference', label: '推理测试', description: '模型测试', icon: <ThunderboltOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  { path: '/evaluation', label: '评估对比', description: '效果验证', icon: <FileSearchOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  { path: '/deployment', label: '部署接入', description: '应用集成', icon: <ApiOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  { path: '/knowledge', label: '知识库', description: 'RAG 检索', icon: <BookOutlined />, groups: ['core'], surfaces: ['sidebar', 'mobile'] },
  { path: '/memory', label: '智能记忆', description: '三层记忆系统', icon: <BulbOutlined />, groups: ['beta'], surfaces: ['sidebar', 'mobile'] },
  {
    path: '/workspace',
    label: '工作空间',
    description: '项目管理',
    icon: <AppstoreOutlined />,
    groups: ['beta'],
    surfaces: ['sidebar', 'mobile', 'bottom'],
  },
  { path: '/project-context', label: '项目上下文', description: '代码理解', icon: <CodeOutlined />, groups: ['beta'], surfaces: ['sidebar', 'mobile'] },
  { path: '/gateway', label: 'Gateway', description: '设备配对与路由', icon: <ClusterOutlined />, groups: ['experimental'], surfaces: ['sidebar', 'mobile'] },
  { path: '/heartbeat', label: 'Heartbeat', description: '任务调度验证', icon: <HeartOutlined />, groups: ['experimental'], surfaces: ['sidebar', 'mobile'] },
  { path: '/cua-control', label: 'CUA 控制', groups: [], surfaces: [] },
  { path: '/cua-recorder', label: '动作录制', groups: [], surfaces: [] },
  { path: '/mcp', label: 'MCP 工具', groups: [], surfaces: [] },
  { path: '/design-system', label: '设计系统', groups: [], surfaces: [] },
  { path: '/cloud-api', label: '云端 API', description: 'API Key 管理', icon: <CloudOutlined />, groups: ['support'], surfaces: ['sidebar', 'mobile'] },
  { path: '/feedback', label: '用户反馈', description: '反馈管理', icon: <LikeOutlined />, groups: ['support'], surfaces: ['sidebar'] },
  { path: '/help', label: '帮助中心', description: '使用指南', icon: <QuestionCircleOutlined />, groups: ['support'], surfaces: ['sidebar'] },
];

const navigationGroups: NavigationGroup[] = [
  { id: 'workbench', label: '工作台 (GA)', surfaces: ['sidebar', 'mobile'] },
  { id: 'core', label: '核心功能 (GA)', surfaces: ['sidebar', 'mobile'] },
  { id: 'beta', label: 'Beta 功能', surfaces: ['sidebar', 'mobile'] },
  { id: 'experimental', label: '实验性 (Experimental)', surfaces: ['sidebar', 'mobile'] },
  { id: 'support', label: '支持', surfaces: ['sidebar', 'mobile'] },
];

export function getRouteMetadata(pathname: string): RouteMetadata | undefined {
  return routeMetadata.find((route) => route.path === pathname);
}

export function getRouteTitle(pathname: string): string {
  return getRouteMetadata(pathname)?.label ?? (pathname.startsWith('/share/') ? '共享对话' : '工作台');
}

export function getRouteLabel(route: RouteMetadata, surface: NavigationSurface): string {
  return surface === 'bottom' ? route.mobileLabel ?? route.label : route.label;
}

export function getRouteCapabilityTier(pathname: string): CapabilityTier | undefined {
  return ROUTE_CAPABILITY[pathname]?.tier;
}

export function isRouteVisible(pathname: string, experimentalEnabled: boolean): boolean {
  return getRouteCapabilityTier(pathname) !== 'experimental' || experimentalEnabled;
}

export function getNavigationGroups(surface: Exclude<NavigationSurface, 'bottom'>) {
  return navigationGroups
    .filter((group) => group.surfaces.includes(surface))
    .map((group) => ({
      ...group,
      items: routeMetadata.filter(
        (route) => route.groups?.includes(group.id) && route.surfaces?.includes(surface),
      ),
    }));
}

export function getBottomNavigationItems(): RouteMetadata[] {
  return routeMetadata.filter((route) => route.surfaces?.includes('bottom'));
}
