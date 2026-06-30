import {
  CloseOutlined,
  DownOutlined,
  DoubleRightOutlined,
  ReloadOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { Button, Drawer, Form, Input, Modal, Select, Tooltip } from 'antd';
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import type { AgentHitlDecision } from '../../services/api';
import { useOptionalRuntimeContext } from '../../runtime/RuntimeContext';
import { useResponsive } from '../../hooks/useResponsive';
import AgentAttentionRail from '../components/AgentAttentionRail';
import AgentEnvironmentRail from '../components/AgentEnvironmentRail';
import AgentPanelToolbar from '../components/AgentPanelToolbar';
import AgentSessionRail from '../components/AgentSessionRail';
import AgentTaskComposer from '../components/AgentTaskComposer';
import AgentWorkspaceView from '../components/AgentWorkspaceView';
import {
  persistAgentWorkbenchSettings,
  readAgentWorkbenchSettings,
  type AgentWorkbenchSettings,
} from '../config/workbenchSettings';
import {
  DEFAULT_AGENT_PANEL_LAYOUT,
  MAX_DOCK_WIDTH,
  MAX_SESSION_WIDTH,
  MAX_TERMINAL_HEIGHT,
  MAX_WORKSPACE_SPLIT,
  MIN_DOCK_WIDTH,
  MIN_SESSION_WIDTH,
  MIN_TERMINAL_HEIGHT,
  MIN_WORKSPACE_SPLIT,
  persistAgentPanelLayout,
  readAgentPanelLayout,
  type AgentTaskCenterTab,
  type AgentWorkspacePanelTab,
} from '../config/panelLayout';
import { useAgentWorkbench } from '../runtime/useAgentWorkbench';
import type { AgentRuntimePersistence } from '../runtime/useAgentWorkbench';
import {
  selectAttentionCount,
  selectConnectionLabel,
  selectTimeline,
  selectWorkspaceProjectLabel,
  selectWorkspaceStatus,
} from '../selectors/workbenchSelectors';
import AgentWorkbenchShell from './AgentWorkbenchShell';
import styles from './AgentWorkbench.module.css';
import type { AgentTransport } from '../transport/agentTransport';
import { routeAgentNextAction } from '../commands/nextActionRouting';

const AgentTerminalPanel = lazy(() => import('../components/AgentTerminalPanel'));
const AgentRunTimeline = lazy(() => import('../components/AgentRunTimeline'));
const WORKSPACE_PANEL_TABS: Array<{ key: AgentWorkspacePanelTab; label: string }> = [
  { key: 'files', label: '文件' },
  { key: 'diff', label: 'Diff' },
];
const TASK_CENTER_TABS: Array<{ key: AgentTaskCenterTab; label: string }> = [
  { key: 'plan', label: '计划' },
  { key: 'subagents', label: '子 Agent' },
  { key: 'artifacts', label: '产物' },
  { key: 'environment', label: '环境' },
];
type AgentResizeTarget = 'session' | 'dock' | 'terminal' | 'workspace-split';

export interface AgentWorkbenchPageProps {
  transport?: AgentTransport;
  persistence?: AgentRuntimePersistence;
}

export default function AgentWorkbenchPage({
  transport,
  persistence,
}: AgentWorkbenchPageProps = {}) {
  const { state, actions } = useAgentWorkbench(transport, persistence);
  const runtime = useOptionalRuntimeContext();
  const { isDesktop } = useResponsive();
  const [panelLayout, setPanelLayout] = useState(readAgentPanelLayout);
  const [mobileDockOpen, setMobileDockOpen] = useState(false);
  const [mobileTerminalOpen, setMobileTerminalOpen] = useState(false);
  const [terminalMounted, setTerminalMounted] = useState(panelLayout.terminalOpen);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [subagentOpen, setSubagentOpen] = useState(false);
  const [requestedFilePath, setRequestedFilePath] = useState<string | null>(null);
  const [attentionOpenRequest, setAttentionOpenRequest] = useState(0);
  const [workspaceDirty, setWorkspaceDirty] = useState(false);
  const [settings, setSettings] = useState<AgentWorkbenchSettings>(readAgentWorkbenchSettings);
  const [subagentForm] = Form.useForm<{ agentName: string; description: string }>();
  const rightDockRef = useRef<HTMLElement | null>(null);
  const resizeFrameRef = useRef<number | null>(null);
  const pendingResizeRef = useRef<Partial<typeof panelLayout> | null>(null);
  const resizeStateRef = useRef<{
    type: AgentResizeTarget;
    startX: number;
    startY: number;
    startValue: number;
    containerSize: number;
  } | null>(null);
  const timeline = useMemo(() => selectTimeline(state), [state]);
  const connectionLabel = selectConnectionLabel(state);
  const statusLabel = selectWorkspaceStatus(state);
  const projectLabel = selectWorkspaceProjectLabel(state.workspace);
  const attentionCount = selectAttentionCount(state);
  const activeOperation = state.activeOperation;
  const composerOperation = state.activeSessionId
    ? state.operations[`submit:${state.activeSessionId}`]
      || state.operations[`interrupt:${state.activeSessionId}`]
    : state.operations['submit:new'];
  const subagentOperationKey = state.activeSessionId
    ? `start-subtask:${state.activeSessionId}`
    : null;
  const subagentTargets = state.workspace?.runtime_policy?.async_subagent_targets
    || state.workspace?.runtime?.policy?.async_subagent_targets
    || ['explore', 'review'];
  const agentRuntimeProvider =
    runtime?.derived.activeBackend === 'ollama' && runtime.derived.activeModelId
      ? 'ollama'
      : undefined;
  const agentRuntimeModel = agentRuntimeProvider ? runtime?.derived.activeModelId : undefined;
  const sessionRuntimeProvider = state.session?.provider || undefined;
  const sessionRuntimeModel = state.session?.model || undefined;
  const effectiveAgentProvider = agentRuntimeProvider || sessionRuntimeProvider;
  const effectiveAgentModel = agentRuntimeModel || sessionRuntimeModel;
  const agentRuntimeLabel = effectiveAgentProvider && effectiveAgentModel
    ? `Agent 模型 ${effectiveAgentProvider}:${effectiveAgentModel}`
    : 'Agent 模型自动选择';

  useEffect(() => {
    persistAgentWorkbenchSettings(settings);
  }, [settings]);

  useEffect(() => {
    const timeout = window.setTimeout(() => persistAgentPanelLayout(panelLayout), 120);
    return () => window.clearTimeout(timeout);
  }, [panelLayout]);

  useEffect(() => () => {
    if (resizeFrameRef.current !== null) cancelAnimationFrame(resizeFrameRef.current);
    delete document.body.dataset.agentResizing;
  }, []);

  const scheduleResize = (next: Partial<typeof panelLayout>) => {
    pendingResizeRef.current = { ...pendingResizeRef.current, ...next };
    if (resizeFrameRef.current !== null) return;
    resizeFrameRef.current = requestAnimationFrame(() => {
      const pending = pendingResizeRef.current;
      resizeFrameRef.current = null;
      pendingResizeRef.current = null;
      if (pending) setPanelLayout((current) => ({ ...current, ...pending }));
    });
  };

  const confirmDiscardWorkspaceChanges = useCallback((action: () => void) => {
    if (!workspaceDirty) {
      action();
      return;
    }
    Modal.confirm({
      title: '放弃未保存的文件修改？',
      content: '切换任务会丢失当前编辑器中尚未保存的内容。',
      okText: '放弃并切换',
      okButtonProps: { danger: true },
      cancelText: '继续编辑',
      onOk: action,
    });
  }, [workspaceDirty]);

  const toggleWorkspace = useCallback(() => {
    if (!isDesktop) {
      if (mobileDockOpen && panelLayout.workspaceOpen) {
        setMobileDockOpen(false);
        return;
      }
      setPanelLayout((current) => ({ ...current, workspaceOpen: true }));
      setMobileDockOpen(true);
      return;
    }
    setPanelLayout((current) => ({ ...current, workspaceOpen: !current.workspaceOpen }));
  }, [isDesktop, mobileDockOpen, panelLayout.workspaceOpen]);

  const toggleTaskCenter = useCallback(() => {
    if (!isDesktop) {
      if (mobileDockOpen && panelLayout.taskCenterOpen) {
        setMobileDockOpen(false);
        return;
      }
      setPanelLayout((current) => ({ ...current, taskCenterOpen: true }));
      setMobileDockOpen(true);
      return;
    }
    setPanelLayout((current) => ({ ...current, taskCenterOpen: !current.taskCenterOpen }));
  }, [isDesktop, mobileDockOpen, panelLayout.taskCenterOpen]);

  const toggleTerminal = useCallback(() => {
    setTerminalMounted(true);
    if (!isDesktop) {
      setMobileTerminalOpen((current) => !current);
      return;
    }
    setPanelLayout((current) => ({ ...current, terminalOpen: !current.terminalOpen }));
  }, [isDesktop]);

  const collapseWorkspace = useCallback(() => {
    if (!isDesktop && !panelLayout.taskCenterOpen) setMobileDockOpen(false);
    setPanelLayout((current) => ({ ...current, workspaceOpen: false }));
  }, [isDesktop, panelLayout.taskCenterOpen]);

  const collapseTaskCenter = useCallback(() => {
    if (!isDesktop && !panelLayout.workspaceOpen) setMobileDockOpen(false);
    setPanelLayout((current) => ({ ...current, taskCenterOpen: false }));
  }, [isDesktop, panelLayout.workspaceOpen]);

  const openWorkspaceTab = useCallback((tab: AgentWorkspacePanelTab) => {
    setPanelLayout((current) => ({ ...current, workspaceOpen: true, workspaceTab: tab }));
    if (!isDesktop) setMobileDockOpen(true);
  }, [isDesktop]);

  const openTaskCenterTab = useCallback((tab: AgentTaskCenterTab) => {
    setPanelLayout((current) => ({ ...current, taskCenterOpen: true, taskCenterTab: tab }));
    if (!isDesktop) setMobileDockOpen(true);
  }, [isDesktop]);

  const openTerminal = useCallback(() => {
    setTerminalMounted(true);
    setPanelLayout((current) => ({ ...current, terminalOpen: true }));
    if (!isDesktop) setMobileTerminalOpen(true);
  }, [isDesktop]);

  useEffect(() => {
    const togglePanelShortcut = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (event.shiftKey && key === 'e') {
        event.preventDefault();
        toggleWorkspace();
      } else if (event.shiftKey && key === 'j') {
        event.preventDefault();
        toggleTaskCenter();
      } else if (!event.shiftKey && event.key === '`') {
        event.preventDefault();
        toggleTerminal();
      }
    };
    window.addEventListener('keydown', togglePanelShortcut);
    return () => window.removeEventListener('keydown', togglePanelShortcut);
  }, [toggleTaskCenter, toggleTerminal, toggleWorkspace]);

  const beginResize = (
    type: AgentResizeTarget,
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    if (!isDesktop) return;
    const startValue = type === 'session'
      ? panelLayout.sessionWidth
      : type === 'dock'
        ? panelLayout.dockWidth
        : type === 'terminal'
          ? panelLayout.terminalHeight
          : panelLayout.workspaceSplit;
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeStateRef.current = {
      type,
      startX: event.clientX,
      startY: event.clientY,
      startValue,
      containerSize: rightDockRef.current?.clientHeight || 1,
    };
    event.currentTarget.dataset.dragging = 'true';
    document.body.dataset.agentResizing = type;
  };

  const resizePanel = (event: ReactPointerEvent<HTMLDivElement>) => {
    const resize = resizeStateRef.current;
    if (!resize) return;
    switch (resize.type) {
      case 'session': {
        const visibleDockWidth = panelLayout.workspaceOpen || panelLayout.taskCenterOpen
          ? Math.max(MIN_DOCK_WIDTH, Math.min(panelLayout.dockWidth, window.innerWidth * 0.46))
          : 0;
        const maximum = Math.min(
          MAX_SESSION_WIDTH,
          Math.max(MIN_SESSION_WIDTH, window.innerWidth - visibleDockWidth - 320),
        );
        const sessionWidth = Math.min(
          maximum,
          Math.max(MIN_SESSION_WIDTH, resize.startValue + event.clientX - resize.startX),
        );
        scheduleResize({ sessionWidth: Math.round(sessionWidth) });
        break;
      }
      case 'dock': {
        const maximum = Math.min(
          MAX_DOCK_WIDTH,
          Math.max(MIN_DOCK_WIDTH, window.innerWidth - panelLayout.sessionWidth - 320),
        );
        const dockWidth = Math.min(
          maximum,
          Math.max(MIN_DOCK_WIDTH, resize.startValue + resize.startX - event.clientX),
        );
        scheduleResize({ dockWidth: Math.round(dockWidth) });
        break;
      }
      case 'terminal': {
        const terminalHeight = Math.min(
          MAX_TERMINAL_HEIGHT,
          Math.max(MIN_TERMINAL_HEIGHT, resize.startValue + resize.startY - event.clientY),
        );
        scheduleResize({ terminalHeight: Math.round(terminalHeight) });
        break;
      }
      case 'workspace-split': {
        const workspaceSplit = Math.min(
          MAX_WORKSPACE_SPLIT,
          Math.max(
            MIN_WORKSPACE_SPLIT,
            resize.startValue + ((event.clientY - resize.startY) / resize.containerSize) * 100,
          ),
        );
        scheduleResize({ workspaceSplit: Math.round(workspaceSplit) });
        break;
      }
    }
  };

  const endResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!resizeStateRef.current) return;
    resizeStateRef.current = null;
    delete event.currentTarget.dataset.dragging;
    delete document.body.dataset.agentResizing;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const resizePanelWithKeyboard = (
    type: AgentResizeTarget,
    event: ReactKeyboardEvent<HTMLDivElement>,
  ) => {
    const step = event.shiftKey ? 40 : 16;
    if (type === 'session' && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      const direction = event.key === 'ArrowRight' ? 1 : -1;
      setPanelLayout((current) => {
        const visibleDockWidth = current.workspaceOpen || current.taskCenterOpen
          ? Math.max(MIN_DOCK_WIDTH, Math.min(current.dockWidth, window.innerWidth * 0.46))
          : 0;
        const maximum = Math.min(
          MAX_SESSION_WIDTH,
          Math.max(MIN_SESSION_WIDTH, window.innerWidth - visibleDockWidth - 320),
        );
        return {
          ...current,
          sessionWidth: Math.round(Math.min(
            maximum,
            Math.max(MIN_SESSION_WIDTH, current.sessionWidth + direction * step),
          )),
        };
      });
    }
    if (type === 'dock' && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      const direction = event.key === 'ArrowLeft' ? 1 : -1;
      setPanelLayout((current) => {
        const maximum = Math.min(
          MAX_DOCK_WIDTH,
          Math.max(MIN_DOCK_WIDTH, window.innerWidth - current.sessionWidth - 320),
        );
        return {
          ...current,
          dockWidth: Math.round(Math.min(
            maximum,
            Math.max(MIN_DOCK_WIDTH, current.dockWidth + direction * step),
          )),
        };
      });
    }
    if (type === 'terminal' && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault();
      const direction = event.key === 'ArrowUp' ? 1 : -1;
      setPanelLayout((current) => ({
        ...current,
        terminalHeight: Math.min(
          MAX_TERMINAL_HEIGHT,
          Math.max(MIN_TERMINAL_HEIGHT, current.terminalHeight + direction * step),
        ),
      }));
    }
    if (type === 'workspace-split' && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault();
      const splitStep = event.shiftKey ? 10 : 2;
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      setPanelLayout((current) => ({
        ...current,
        workspaceSplit: Math.min(
          MAX_WORKSPACE_SPLIT,
          Math.max(MIN_WORKSPACE_SPLIT, current.workspaceSplit + direction * splitStep),
        ),
      }));
    }
  };

  const resetPanelSize = (type: AgentResizeTarget) => {
    setPanelLayout((current) => ({
      ...current,
      ...(type === 'session' && { sessionWidth: DEFAULT_AGENT_PANEL_LAYOUT.sessionWidth }),
      ...(type === 'dock' && { dockWidth: DEFAULT_AGENT_PANEL_LAYOUT.dockWidth }),
      ...(type === 'terminal' && { terminalHeight: DEFAULT_AGENT_PANEL_LAYOUT.terminalHeight }),
      ...(type === 'workspace-split' && {
        workspaceSplit: DEFAULT_AGENT_PANEL_LAYOUT.workspaceSplit,
      }),
    }));
  };

  const decidePermission = (partId: string, decisions: AgentHitlDecision[]) => {
    void actions.decidePermission(partId, decisions);
  };

  const runNextAction = (action: Parameters<typeof routeAgentNextAction>[0]) => {
    const intent = routeAgentNextAction(
      action,
      state.workspace?.async_tasks.tasks || [],
    );
    switch (intent.type) {
      case 'start_subagent':
        void actions.startSubagent(intent.agentName, intent.description);
        openTaskCenterTab('subagents');
        break;
      case 'open_attention':
        setAttentionOpenRequest((current) => current + 1);
        break;
      case 'open_tab':
        if (intent.filePath) setRequestedFilePath(intent.filePath);
        if (intent.tab === 'files' || intent.tab === 'diff') {
          openWorkspaceTab(intent.tab);
        } else if (intent.tab === 'terminal') {
          openTerminal();
        } else if (intent.tab !== 'activity') {
          openTaskCenterTab(intent.tab);
        }
        break;
      case 'submit_prompt':
        void actions.submitTask({
          content: intent.content,
          agentId: state.session?.agent_id || 'build',
          provider: effectiveAgentProvider,
          model: effectiveAgentModel,
        });
        break;
    }
  };

  const sessionRail = (embedded = false) => (
    <AgentSessionRail
      embedded={embedded}
      sessions={state.recentSessions}
      activeSessionId={state.activeSessionId}
      onNew={() => {
        confirmDiscardWorkspaceChanges(() => {
          actions.newSession();
        });
      }}
      onSelect={(sessionId) => {
        if (sessionId === state.activeSessionId) return;
        confirmDiscardWorkspaceChanges(() => {
          actions.selectSession(sessionId);
        });
      }}
      onUpdatePreferences={actions.updateSessionPreferences}
    />
  );
  const attentionRail = (embedded = false) => (
    <AgentAttentionRail
      embedded={embedded}
      state={state}
      workspace={state.workspace}
      onClearError={actions.clearError}
      onRefresh={() => void actions.refresh()}
      onDecidePermission={decidePermission}
      onRecoverNode={(node) => void actions.recoverNode(node)}
      onRestartSubagent={(agentName, description) => void actions.startSubagent(agentName, description)}
    />
  );
  const environmentRail = (
    <AgentEnvironmentRail
      state={state}
      connection={state.connection}
      connectionLabel={connectionLabel}
      onOpenSettings={() => setSettingsOpen(true)}
    />
  );
  const toolbar = (
    <>
      {state.activeSessionId ? (
        <Tooltip title="刷新权威快照">
          <Button
            type="text"
            icon={<ReloadOutlined />}
            loading={Boolean(state.operations[`refresh:${state.activeSessionId}`])}
            onClick={() => void actions.refresh()}
            aria-label="刷新运行"
          />
        </Tooltip>
      ) : null}
          <Tooltip title="新建子 Agent">
            <Button
              type="text"
              icon={<TeamOutlined />}
              disabled={!state.activeSessionId}
              onClick={() => setSubagentOpen(true)}
              aria-label="新建子 Agent"
            />
          </Tooltip>
          <Tooltip title="工作台设置">
            <Button
              type="text"
              icon={<SettingOutlined />}
              onClick={() => setSettingsOpen(true)}
              aria-label="工作台设置"
            />
          </Tooltip>
    </>
  );

  const rightDockVisible = isDesktop
    ? panelLayout.workspaceOpen || panelLayout.taskCenterOpen
    : mobileDockOpen;
  const terminalVisible = isDesktop ? panelLayout.terminalOpen : mobileTerminalOpen;
  const surfaceStyle = {
    '--agent-dock-width': `${panelLayout.dockWidth}px`,
    '--agent-terminal-height': `${panelLayout.terminalHeight}px`,
    '--agent-workspace-split': `${panelLayout.workspaceSplit}%`,
  } as CSSProperties;
  const workspacePanel = (
    <AgentWorkspaceView
      key={`workspace:${state.workspace?.session.id || 'empty'}`}
      tab={panelLayout.workspaceTab}
      workspace={state.workspace}
      busyKey={activeOperation?.key}
      requestedFilePath={requestedFilePath}
      onRecover={(node) => void actions.recoverNode(node)}
      onCancelSubagent={(taskId) => void actions.cancelSubagent(taskId)}
      onDirtyChange={setWorkspaceDirty}
      onRunNextAction={runNextAction}
    />
  );
  const taskCenterPanel = panelLayout.taskCenterTab === 'environment'
    ? environmentRail
    : (
      <AgentWorkspaceView
        key={`tasks:${state.workspace?.session.id || 'empty'}`}
        tab={panelLayout.taskCenterTab}
        workspace={state.workspace}
        busyKey={activeOperation?.key}
        requestedFilePath={null}
        onRecover={(node) => void actions.recoverNode(node)}
        onCancelSubagent={(taskId) => void actions.cancelSubagent(taskId)}
        onRunNextAction={runNextAction}
      />
    );

  return (
    <AgentWorkbenchShell
      title={state.session?.title || '新任务'}
      subtitle={`${projectLabel} · ${statusLabel} · ${agentRuntimeLabel}`}
      connection={state.connection}
      connectionLabel={connectionLabel}
      attentionCount={attentionCount}
      attentionOpenRequest={attentionOpenRequest}
      sessionWidth={panelLayout.sessionWidth}
      desktopSessionRail={(
        <>
          {sessionRail()}
          <div
            className={styles.sessionResizeHandle}
            role="separator"
            aria-label="调整会话栏宽度"
            aria-orientation="vertical"
            aria-valuemin={MIN_SESSION_WIDTH}
            aria-valuemax={MAX_SESSION_WIDTH}
            aria-valuenow={panelLayout.sessionWidth}
            tabIndex={isDesktop ? 0 : -1}
            title="拖动调整，双击恢复默认宽度"
            onDoubleClick={() => resetPanelSize('session')}
            onKeyDown={(event) => resizePanelWithKeyboard('session', event)}
            onPointerDown={(event) => beginResize('session', event)}
            onPointerMove={resizePanel}
            onPointerUp={endResize}
            onPointerCancel={endResize}
          />
        </>
      )}
      mobileSessionRail={sessionRail(true)}
      mobileAttentionRail={attentionRail(true)}
      toolbar={toolbar}
    >
      <main
        className={styles.mainSurface}
        style={surfaceStyle}
        data-dock-visible={rightDockVisible ? 'true' : 'false'}
      >
        <section className={styles.conversationColumn} aria-label="Agent 运行区">
          <div className={styles.conversationFrame}>
            <AgentPanelToolbar
              workspaceOpen={isDesktop
                ? panelLayout.workspaceOpen
                : mobileDockOpen && panelLayout.workspaceOpen}
              taskCenterOpen={isDesktop
                ? panelLayout.taskCenterOpen
                : mobileDockOpen && panelLayout.taskCenterOpen}
              terminalOpen={terminalVisible}
              onToggleWorkspace={toggleWorkspace}
              onToggleTaskCenter={toggleTaskCenter}
              onToggleTerminal={toggleTerminal}
            />
            <div className={styles.contentSurface}>
            <Suspense fallback={<div className={styles.panelLoading}>正在加载运行记录...</div>}>
              <AgentRunTimeline
                timeline={timeline}
                pendingLabel={composerOperation?.key.startsWith('submit:') ? composerOperation.label : undefined}
                errorMessage={state.error}
              />
            </Suspense>
            </div>
          </div>
          <AgentTaskComposer
            agents={state.agents}
            session={state.session}
            busy={Boolean(composerOperation)}
            busyLabel={composerOperation?.label}
            onSubmit={(content, agentId) => actions.submitTask({
              content,
              agentId,
              projectPath: settings.projectPath,
              provider: effectiveAgentProvider,
              model: effectiveAgentModel,
              autonomyMode: settings.autonomyMode,
            })}
            onInterrupt={actions.interrupt}
          />
          <section
            className={styles.terminalDock}
            data-visible={terminalVisible ? 'true' : 'false'}
            aria-label="终端面板"
            aria-hidden={!terminalVisible}
          >
            <div
              className={styles.terminalResizeHandle}
              role="separator"
              aria-label="调整终端高度"
              aria-orientation="horizontal"
              aria-valuemin={MIN_TERMINAL_HEIGHT}
              aria-valuemax={MAX_TERMINAL_HEIGHT}
              aria-valuenow={panelLayout.terminalHeight}
              tabIndex={isDesktop ? 0 : -1}
              title="拖动调整，双击恢复默认高度"
              onDoubleClick={() => resetPanelSize('terminal')}
              onKeyDown={(event) => resizePanelWithKeyboard('terminal', event)}
              onPointerDown={(event) => beginResize('terminal', event)}
              onPointerMove={resizePanel}
              onPointerUp={endResize}
              onPointerCancel={endResize}
            />
            <header className={styles.terminalDockHeader}>
              <div><strong>终端 1</strong><span>测试</span></div>
              <Tooltip title="隐藏终端">
                <button
                  type="button"
                  aria-label="隐藏终端"
                  onClick={() => {
                    if (isDesktop) {
                      setPanelLayout((current) => ({ ...current, terminalOpen: false }));
                    } else {
                      setMobileTerminalOpen(false);
                    }
                  }}
                >
                  <DownOutlined />
                </button>
              </Tooltip>
            </header>
            <div className={styles.terminalDockBody}>
              {terminalMounted ? (
                <Suspense fallback={<div className={styles.panelLoading}>正在加载终端...</div>}>
                  <AgentTerminalPanel timeline={timeline} />
                </Suspense>
              ) : null}
            </div>
          </section>
        </section>

        <aside
          ref={rightDockRef}
          className={styles.rightDock}
          data-visible={rightDockVisible ? 'true' : 'false'}
          data-workspace-open={panelLayout.workspaceOpen ? 'true' : 'false'}
          data-tasks-open={panelLayout.taskCenterOpen ? 'true' : 'false'}
          aria-label="工作台侧栏"
          aria-hidden={!rightDockVisible}
        >
          <div
            className={styles.dockResizeHandle}
            role="separator"
            aria-label="调整工作区宽度"
            aria-orientation="vertical"
            aria-valuemin={MIN_DOCK_WIDTH}
            aria-valuemax={MAX_DOCK_WIDTH}
            aria-valuenow={panelLayout.dockWidth}
            tabIndex={isDesktop ? 0 : -1}
            title="拖动调整，双击恢复默认宽度"
            onDoubleClick={() => resetPanelSize('dock')}
            onKeyDown={(event) => resizePanelWithKeyboard('dock', event)}
            onPointerDown={(event) => beginResize('dock', event)}
            onPointerMove={resizePanel}
            onPointerUp={endResize}
            onPointerCancel={endResize}
          />
          <button
            type="button"
            className={styles.mobileDockClose}
            aria-label="关闭工作台侧栏"
            onClick={() => setMobileDockOpen(false)}
          >
            <CloseOutlined />
          </button>
          <section className={styles.workspaceDockPanel} hidden={!panelLayout.workspaceOpen} aria-label="工作区">
            <header className={styles.idePanelHeader}>
              <div role="tablist" aria-label="工作区视图">
                {WORKSPACE_PANEL_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    role="tab"
                    aria-selected={panelLayout.workspaceTab === tab.key}
                    className={panelLayout.workspaceTab === tab.key ? styles.ideTabActive : styles.ideTab}
                    onClick={() => openWorkspaceTab(tab.key)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <Tooltip title="隐藏工作区">
                <button
                  type="button"
                  aria-label="隐藏工作区"
                  onClick={collapseWorkspace}
                >
                  <DoubleRightOutlined />
                </button>
              </Tooltip>
            </header>
            <div className={styles.idePanelBody}>{workspacePanel}</div>
          </section>
          {panelLayout.workspaceOpen && panelLayout.taskCenterOpen ? (
            <div
              className={styles.workspaceSplitResizeHandle}
              role="separator"
              aria-label="调整工作区与任务中心比例"
              aria-orientation="horizontal"
              aria-valuemin={MIN_WORKSPACE_SPLIT}
              aria-valuemax={MAX_WORKSPACE_SPLIT}
              aria-valuenow={panelLayout.workspaceSplit}
              tabIndex={isDesktop ? 0 : -1}
              title="拖动调整，双击恢复默认比例"
              onDoubleClick={() => resetPanelSize('workspace-split')}
              onKeyDown={(event) => resizePanelWithKeyboard('workspace-split', event)}
              onPointerDown={(event) => beginResize('workspace-split', event)}
              onPointerMove={resizePanel}
              onPointerUp={endResize}
              onPointerCancel={endResize}
            />
          ) : null}
          <section className={styles.taskCenterDockPanel} hidden={!panelLayout.taskCenterOpen} aria-label="任务中心">
            <header className={styles.idePanelHeader}>
              <div className={styles.taskCenterTitle}>任务中心</div>
              <Tooltip title="隐藏任务中心">
                <button
                  type="button"
                  aria-label="隐藏任务中心"
                  onClick={collapseTaskCenter}
                >
                  <DoubleRightOutlined />
                </button>
              </Tooltip>
            </header>
            <nav className={styles.taskCenterTabs} aria-label="任务中心视图">
              {TASK_CENTER_TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  aria-current={panelLayout.taskCenterTab === tab.key ? 'page' : undefined}
                  className={panelLayout.taskCenterTab === tab.key ? styles.ideTabActive : styles.ideTab}
                  onClick={() => openTaskCenterTab(tab.key)}
                >
                  {tab.label}
                  {tab.key === 'subagents' && state.workspace?.async_tasks.metrics.attention ? (
                    <span className={styles.tabCount}>{state.workspace.async_tasks.metrics.attention}</span>
                  ) : null}
                </button>
              ))}
            </nav>
            <div className={styles.idePanelBody}>{taskCenterPanel}</div>
          </section>
        </aside>

        {!isDesktop && (mobileDockOpen || mobileTerminalOpen) ? (
          <button
            type="button"
            className={styles.mobilePanelBackdrop}
            aria-label="关闭浮动面板"
            onClick={() => {
              setMobileDockOpen(false);
              setMobileTerminalOpen(false);
            }}
          />
        ) : null}
      </main>

      <Drawer
        title="工作台设置"
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        width={360}
      >
        <Form layout="vertical">
          <Form.Item label="项目路径" extra="留空时使用后端默认工作区。新会话创建后不可修改。">
            <Input
              value={settings.projectPath}
              disabled={Boolean(state.session)}
              placeholder="C:\\path\\to\\project"
              onChange={(event) => setSettings((current) => ({
                ...current,
                projectPath: event.target.value,
              }))}
            />
          </Form.Item>
          <Form.Item label="自主模式">
            <Select
              value={settings.autonomyMode}
              disabled={Boolean(state.session)}
              onChange={(autonomyMode) => setSettings((current) => ({ ...current, autonomyMode }))}
              options={[
                { value: 'safe_auto', label: '安全自动' },
                { value: 'confirm_all', label: '全部确认' },
                { value: 'read_only', label: '只读' },
              ]}
            />
          </Form.Item>
        </Form>
      </Drawer>

      <Modal
        title="启动子 Agent"
        open={subagentOpen}
        okText="启动"
        cancelText="取消"
        confirmLoading={Boolean(subagentOperationKey && state.operations[subagentOperationKey])}
        onCancel={() => setSubagentOpen(false)}
        onOk={() => {
          void subagentForm.validateFields().then(async (values) => {
            try {
              await actions.startSubagent(values.agentName, values.description);
              subagentForm.resetFields();
              setSubagentOpen(false);
              openTaskCenterTab('subagents');
            } catch {
              // Runtime state already exposes the actionable error; keep the modal open for retry.
            }
          });
        }}
      >
        <Form
          form={subagentForm}
          layout="vertical"
          initialValues={{ agentName: subagentTargets[0] || 'explore' }}
        >
          <Form.Item name="agentName" label="Agent" rules={[{ required: true }]}>
            <Select options={subagentTargets.map((target) => ({ value: target, label: target }))} />
          </Form.Item>
          <Form.Item name="description" label="任务说明" rules={[{ required: true, min: 3 }]}>
            <Input.TextArea rows={4} placeholder="说明希望子 Agent 独立完成的工作" />
          </Form.Item>
        </Form>
      </Modal>
    </AgentWorkbenchShell>
  );
}
