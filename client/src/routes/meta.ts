/** Single source of truth for route labels in the shell and browser title. */
export const ROUTE_TITLES: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/device': '设备信息',
  '/models': '模型运行中心',
  '/datasets': '数据集',
  '/training': '模型训练',
  '/chat': 'AI 对话',
  '/agent': 'Agent 工作台',
  '/knowledge': '知识库',
  '/workspace': '工作空间',
  '/memory': '智能记忆',
  '/modelhub': '模型运行中心',
  '/inference': '推理测试',
  '/evaluation': '评估对比',
  '/deployment': '部署接入',
  '/history': '训练历史',
  '/training-compare': '训练对比',
  '/project-context': '项目上下文',
  '/cloud-api': '云端 API',
  '/cua-control': 'CUA 控制',
  '/cua-recorder': '动作录制',
  '/mcp': 'MCP 工具',
  '/gateway': 'Gateway',
  '/heartbeat': 'Heartbeat',
  '/design-system': '设计系统',
  '/feedback': '用户反馈',
  '/help': '帮助中心',
};

export function getRouteTitle(pathname: string): string {
  return ROUTE_TITLES[pathname] || (pathname.startsWith('/share/') ? '共享对话' : '工作台');
}
