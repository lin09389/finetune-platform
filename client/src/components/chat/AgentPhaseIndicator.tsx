import React, { useState, useEffect } from 'react';

interface AgentPhaseIndicatorProps {
  phase: string;
  tool?: string;
  visible: boolean;
}

type PhaseConfig = { icon: string; label: string; sublabel?: string };

const phaseConfig: Record<string, PhaseConfig> = {
  model_thinking: { icon: 'thinking', label: '思考中', sublabel: '正在分析你的请求...' },
  model_thinking_fallback: { icon: 'thinking', label: '模型调用中', sublabel: '回退到非流式模式...' },
  model_streaming: { icon: 'writing', label: '生成中', sublabel: '正在输出内容...' },
  tool_execution: { icon: 'tool', label: '执行工具', sublabel: undefined },
  tool_completed: { icon: 'check', label: '工具完成', sublabel: '准备继续...' },
  model_stream_failed: { icon: 'warning', label: '流式输出失败', sublabel: '正在回退...' },
};

const toolNameMap: Record<string, string> = {
  read: '读取文件',
  search: '搜索代码',
  collect_context: '收集上下文',
  detect_project_commands: '检测项目命令',
  patch: '修改文件',
  bash_command: '执行命令',
  finalize: '生成总结',
};

function PhaseIcon({ icon }: { icon: string }) {
  switch (icon) {
    case 'thinking':
      return (
        <span className="agent-phase-icon agent-phase-icon-thinking">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="3" cy="8" r="2" fill="currentColor" opacity="0.4" />
            <circle cx="8" cy="8" r="2" fill="currentColor" opacity="0.7" />
            <circle cx="13" cy="8" r="2" fill="currentColor" />
          </svg>
        </span>
      );
    case 'writing':
      return (
        <span className="agent-phase-icon agent-phase-icon-writing">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M12 2L14 4L5 13H3V11L12 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
        </span>
      );
    case 'tool':
      return (
        <span className="agent-phase-icon agent-phase-icon-tool">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M6 2L10 6L6 10L2 6L6 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            <path d="M10 6L14 10L10 14L6 10L10 6Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
        </span>
      );
    case 'check':
      return (
        <span className="agent-phase-icon agent-phase-icon-check">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8L7 12L13 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      );
    case 'warning':
      return (
        <span className="agent-phase-icon agent-phase-icon-warning">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3L14 13H2L8 3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            <line x1="8" y1="7" x2="8" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="8" cy="11.5" r="0.5" fill="currentColor" />
          </svg>
        </span>
      );
    default:
      return (
        <span className="agent-phase-icon agent-phase-icon-default">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </span>
      );
  }
}

const AgentPhaseIndicator = React.memo(function AgentPhaseIndicator({ phase, tool, visible }: AgentPhaseIndicatorProps) {
  const [show, setShow] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      requestAnimationFrame(() => setShow(true));
    } else {
      setShow(false);
      const timer = setTimeout(() => setMounted(false), 300);
      return () => clearTimeout(timer);
    }
  }, [visible]);

  if (!mounted) return null;

  const defaultConfig: PhaseConfig = { icon: 'thinking', label: '处理中', sublabel: '请稍候...' };
  const safeConfig: PhaseConfig = (phase && phaseConfig[phase]) || defaultConfig;
  const toolLabel = tool ? toolNameMap[tool] || tool : undefined;
  const transitionPhases = ['tool_completed'];
  const isTransient = transitionPhases.includes(phase);

  return (
    <div
      className={`agent-phase-indicator ${show ? 'agent-phase-indicator-visible' : ''} ${isTransient ? 'agent-phase-indicator-transient' : ''}`}
    >
      <span className="agent-phase-spinner">
        <PhaseIcon icon={safeConfig.icon} />
      </span>
      <span className="agent-phase-text">
        <span className="agent-phase-label">{safeConfig.label}</span>
        {toolLabel && <span className="agent-phase-tool">{toolLabel}</span>}
        {safeConfig.sublabel && !toolLabel && <span className="agent-phase-sub">{safeConfig.sublabel}</span>}
      </span>
    </div>
  );
});

export default AgentPhaseIndicator;