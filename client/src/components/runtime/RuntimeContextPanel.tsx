import React from 'react'
import { ReloadOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import InsightPanel from '../shared/InsightPanel'
import { useRuntimeContext } from '../../runtime/RuntimeContext'

interface RuntimeContextPanelProps {
  page: 'training' | 'inference' | 'knowledge' | 'chat'
}

const pageLabels: Record<RuntimeContextPanelProps['page'], string> = {
  training: '训练运行上下文',
  inference: '推理运行上下文',
  knowledge: '知识运行上下文',
  chat: '会话运行上下文',
}

const RuntimeContextPanel: React.FC<RuntimeContextPanelProps> = ({ page }) => {
  const runtime = useRuntimeContext()
  const [refreshing, setRefreshing] = React.useState(false)

  const statusMap = {
    ready: { type: 'success' as const, text: '上下文就绪' },
    degraded: { type: 'warning' as const, text: '上下文受限' },
    offline: { type: 'error' as const, text: '后端离线' },
  }

  const handleRefresh = async () => {
    if (refreshing) return

    setRefreshing(true)
    try {
      await runtime.actions.refreshBootstrap()
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <InsightPanel
      embedded
      title={pageLabels[page]}
      status={statusMap[runtime.derived.runtimeStatus]}
      summary="这块区域统一承载当前页面依赖的后端、模型、知识集合和依赖就绪状态，后续会逐步承接恢复动作与跨页面连续流。"
      actions={
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={refreshing}
          disabled={runtime.observed.backendStatus !== 'connected'}
          onClick={handleRefresh}
        >
          刷新运行上下文
        </Button>
      }
      metrics={[
        {
          label: '活跃后端',
          value: runtime.derived.activeBackend || '-',
        },
        {
          label: '活跃模型',
          value: runtime.derived.activeModelId || '未选择',
        },
        {
          label: '知识集合',
          value: runtime.derived.activeKnowledgeCollection || 'default',
        },
        {
          label: '可用模型数',
          value: runtime.derived.availableModelCount,
          hint: runtime.derived.activeBackend === 'ollama' && !runtime.observed.inference.ollamaAvailable
            ? 'Ollama 当前不可用'
            : '按当前后端统计',
        },
      ]}
      sections={[
        {
          title: '运行风险',
          items: runtime.derived.warnings,
          tone: 'warning',
        },
      ]}
      testId={`runtime-context-${page}`}
    />
  )
}

export default RuntimeContextPanel
