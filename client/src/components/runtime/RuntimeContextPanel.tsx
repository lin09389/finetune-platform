import { ReloadOutlined, DownOutlined, UpOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import React, { useState } from 'react';
import { useRuntimeContext } from '../../runtime/RuntimeContext';
import InsightPanel from '../shared/InsightPanel';

interface RuntimeContextPanelProps {
  page: 'training' | 'inference' | 'knowledge' | 'chat';
}

const pageLabels: Record<RuntimeContextPanelProps['page'], string> = {
  training: '训练运行上下文',
  inference: '推理运行上下文',
  knowledge: '知识运行上下文',
  chat: '会话运行上下文',
};

const RuntimeContextPanel: React.FC<RuntimeContextPanelProps> = ({ page }) => {
  const runtime = useRuntimeContext();
  const [refreshing, setRefreshing] = React.useState(false);
  const [expanded, setExpanded] = useState(false);

  const trainingSignal = runtime.derived.trainingSignal || {
    phase: 'idle',
    label: '训练空闲',
    tone: 'info' as const,
  };
  const trainingProgressMessage = runtime.observed.training?.progressMessage;

  const statusMap = {
    ready: { type: 'success' as const, text: '上下文就绪', color: 'var(--success)' },
    degraded: { type: 'warning' as const, text: '上下文受限', color: 'var(--warning)' },
    offline: { type: 'error' as const, text: '后端离线', color: 'var(--error)' },
  };

  const handleRefresh = async (e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (refreshing) return;

    setRefreshing(true);
    try {
      await runtime.actions.refreshBootstrap();
    } finally {
      setRefreshing(false);
    }
  };

  const panelContent = (
    <InsightPanel
      embedded={page === 'chat' ? true : false}
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
          hint:
            runtime.derived.activeBackend === 'ollama' &&
            !runtime.observed.inference.ollamaAvailable
              ? 'Ollama 当前不可用'
              : '按当前后端统计',
        },
        {
          label: '训练阶段',
          value: trainingSignal.label,
          hint:
            trainingProgressMessage ||
            '统一枚举状态（idle/loading/training/running/stopping/stopped/completed/failed）',
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
  );

  // 对话页面使用更优雅的悬浮折叠栏，降低突兀感
  if (page === 'chat') {
    const isError = runtime.derived.runtimeStatus === 'offline';
    return (
      <div style={{ marginBottom: 16 }}>
        <div 
          onClick={() => setExpanded(!expanded)}
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            padding: '8px 16px', 
            background: isError ? 'rgba(255,77,79,0.05)' : 'var(--bg-elevated)', 
            border: `1px solid ${isError ? 'rgba(255,77,79,0.2)' : 'var(--border-color)'}`,
            borderRadius: expanded ? '12px 12px 0 0' : '12px',
            cursor: 'pointer',
            transition: 'all 0.3s ease',
            fontSize: 13
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ 
              width: 8, height: 8, borderRadius: '50%', 
              background: statusMap[runtime.derived.runtimeStatus].color,
              boxShadow: `0 0 8px ${statusMap[runtime.derived.runtimeStatus].color}`
            }} />
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{pageLabels[page]}</span>
            <span style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>
              后端: {runtime.derived.activeBackend || '无'} · 
              模型: {runtime.derived.activeModelId || '未选择'}
              {trainingSignal.phase !== 'idle' && ` · 状态: 训练中`}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--text-tertiary)' }}>
            {runtime.derived.warnings.length > 0 && (
              <span style={{ color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: 4 }}>
                <InfoCircleOutlined /> {runtime.derived.warnings.length} 个警告
              </span>
            )}
            {expanded ? <UpOutlined style={{ fontSize: 10 }} /> : <DownOutlined style={{ fontSize: 10 }} />}
          </div>
        </div>
        
        {expanded && (
          <div style={{ 
            padding: 16, 
            background: 'var(--bg-secondary)', 
            border: '1px solid var(--border-color)',
            borderTop: 'none',
            borderRadius: '0 0 12px 12px'
          }}>
            {panelContent}
          </div>
        )}
      </div>
    );
  }

  // 其他页面保持原本的样式 (可能不使用 embedded 以保持阴影卡片效果)
  return (
    <div style={{ marginBottom: 24 }}>
      <InsightPanel
        embedded={false}
        title={pageLabels[page]}
        status={statusMap[runtime.derived.runtimeStatus]}
        summary={expanded ? "这块区域统一承载当前页面依赖的后端、模型、知识集合和依赖就绪状态，后续会逐步承接恢复动作与跨页面连续流。" : undefined}
        actions={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {expanded && (
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={refreshing}
                disabled={runtime.observed.backendStatus !== 'connected'}
                onClick={handleRefresh}
              >
                刷新
              </Button>
            )}
            <Button
              size="small"
              type="text"
              icon={expanded ? <UpOutlined /> : <DownOutlined />}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? '收起' : '展开'}
            </Button>
          </div>
        }
        metrics={
          expanded
            ? [
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
                  hint:
                    runtime.derived.activeBackend === 'ollama' &&
                    !runtime.observed.inference.ollamaAvailable
                      ? 'Ollama 当前不可用'
                      : '按当前后端统计',
                },
                {
                  label: '训练阶段',
                  value: trainingSignal.label,
                  hint:
                    trainingProgressMessage ||
                    '统一枚举状态（idle/loading/training/running/stopping/stopped/completed/failed）',
                },
              ]
            : []
        }
        sections={
          expanded
            ? [
                {
                  title: '运行风险',
                  items: runtime.derived.warnings,
                  tone: 'warning',
                },
              ]
            : []
        }
        testId={`runtime-context-${page}`}
      />
    </div>
  );
};

export default RuntimeContextPanel;
