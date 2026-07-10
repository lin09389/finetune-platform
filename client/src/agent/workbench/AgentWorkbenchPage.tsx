import {
  ReloadOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { Button, Modal, Tooltip, message } from 'antd';
import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import type { AgentHitlDecision } from '../../services/api';
import { useOptionalRuntimeContext } from '../../runtime/RuntimeContext';
import { useResponsive } from '../../hooks/useResponsive';
import AgentAttentionRail from '../components/AgentAttentionRail';
import AgentEnvironmentRail from '../components/AgentEnvironmentRail';
import AgentPanelToolbar from '../components/AgentPanelToolbar';
import AgentResizeHandle from '../components/AgentResizeHandle';
import AgentRightDock from '../components/AgentRightDock';
import AgentSessionRail from '../components/AgentSessionRail';
import AgentTaskComposer from '../components/AgentTaskComposer';
import AgentTerminalDock from '../components/AgentTerminalDock';
import AgentWorkspaceView from '../components/AgentWorkspaceView';
import AgentActivityBar from '../components/AgentActivityBar';
import SubagentModal from '../components/SubagentModal';
import WorkbenchSettingsDrawer from '../components/WorkbenchSettingsDrawer';
import {
  persistAgentWorkbenchSettings,
  readAgentWorkbenchSettings,
  type AgentWorkbenchSettings,
} from '../config/workbenchSettings';
import {
  MAX_SESSION_WIDTH,
  MIN_SESSION_WIDTH,
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
import { selectCurrentActivity } from '../selectors/currentActivity';
import AgentWorkbenchShell from './AgentWorkbenchShell';
import { buildPanelSurfaceStyle, usePanelResize } from './usePanelResize';
import styles from './AgentWorkbench.module.css';
import type { AgentTransport } from '../transport/agentTransport';
import { routeAgentNextAction } from '../commands/nextActionRouting';

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
  const rightDockRef = useRef<HTMLElement | null>(null);
  const resize = usePanelResize({ panelLayout, setPanelLayout, rightDockRef, isDesktop });

  const timeline = useMemo(() => selectTimeline(state), [state]);
  const connectionLabel = selectConnectionLabel(state);
  const statusLabel = selectWorkspaceStatus(state);
  const projectLabel = selectWorkspaceProjectLabel(state.workspace);
  const attentionCount = selectAttentionCount(state);
  const currentActivity = selectCurrentActivity(state);
  const isSessionRunning = Boolean(state.session
    && ['running', 'planning', 'executing', 'verifying', 'repairing'].includes(state.session.status));
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
  const pendingPermissionPartId = state.workspace?.pending_permission?.part_id || null;
  const permissionBusy = Boolean(pendingPermissionPartId
    && state.operations[`permission:${pendingPermissionPartId}`]);
  const subagentAttentionCount = state.workspace?.async_tasks.metrics.attention || 0;
  const subagentRunningCount = state.workspace?.async_tasks.metrics.running || 0;
  const planNodes = state.workspace?.execution_plan?.nodes || [];
  const planTotal = planNodes.length;
  const planCompleted = planNodes.filter((n) => n.status === 'completed').length;
  const recoveredAt = state.recoveredAt;

  useEffect(() => {
    if (!recoveredAt) return;
    const timer = window.setTimeout(() => message.success('已恢复实时同步'), 100);
    return () => window.clearTimeout(timer);
  }, [recoveredAt]);

  useEffect(() => {
    persistAgentWorkbenchSettings(settings);
  }, [settings]);

  useEffect(() => {
    const timeout = window.setTimeout(() => persistAgentPanelLayout(panelLayout), 120);
    return () => window.clearTimeout(timeout);
  }, [panelLayout]);

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

  const closeTerminal = useCallback(() => {
    if (isDesktop) {
      setPanelLayout((current) => ({ ...current, terminalOpen: false }));
    } else {
      setMobileTerminalOpen(false);
    }
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
      unreadSessionIds={state.unreadSessionIds}
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
  const surfaceStyle: CSSProperties = buildPanelSurfaceStyle(panelLayout);
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
          <AgentResizeHandle
            target="session"
            valueNow={panelLayout.sessionWidth}
            valueMin={MIN_SESSION_WIDTH}
            valueMax={MAX_SESSION_WIDTH}
            isDesktop={isDesktop}
            resize={resize}
            className={styles.sessionResizeHandle}
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
              <AgentActivityBar
                activity={currentActivity}
                isRunning={isSessionRunning}
                timelineEmpty={timeline.length === 0}
                connection={state.connection}
                connectionLabel={connectionLabel}
                lastEventAt={state.lastEventAt}
                subagentRunningCount={subagentRunningCount}
                planCompleted={planCompleted}
                planTotal={planTotal}
              />
              <Suspense fallback={<div className={styles.panelLoading}>正在加载运行记录...</div>}>
                <AgentRunTimeline
                  timeline={timeline}
                  pendingLabel={composerOperation?.key.startsWith('submit:') ? composerOperation.label : undefined}
                  errorMessage={state.error}
                  activity={currentActivity}
                  loading={Boolean(state.activeSessionId) && !state.session}
                  pendingPermission={state.workspace?.pending_permission || null}
                  onDecidePermission={decidePermission}
                  permissionBusy={permissionBusy}
                  onOpenFile={(filePath) => {
                    setRequestedFilePath(filePath);
                    openWorkspaceTab('files');
                  }}
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
          <AgentTerminalDock
            visible={terminalVisible}
            mounted={terminalMounted}
            isDesktop={isDesktop}
            terminalHeight={panelLayout.terminalHeight}
            timeline={timeline}
            resize={resize}
            onClose={closeTerminal}
          />
        </section>

        <AgentRightDock
          panelLayout={panelLayout}
          rightDockRef={rightDockRef}
          isDesktop={isDesktop}
          rightDockVisible={rightDockVisible}
          workspaceTabs={WORKSPACE_PANEL_TABS}
          taskCenterTabs={TASK_CENTER_TABS}
          workspacePanel={workspacePanel}
          taskCenterPanel={taskCenterPanel}
          subagentAttentionCount={subagentAttentionCount}
          resize={resize}
          onOpenWorkspaceTab={openWorkspaceTab}
          onOpenTaskCenterTab={openTaskCenterTab}
          onCollapseWorkspace={collapseWorkspace}
          onCollapseTaskCenter={collapseTaskCenter}
          onMobileDockClose={() => setMobileDockOpen(false)}
        />

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

      <WorkbenchSettingsDrawer
        open={settingsOpen}
        settings={settings}
        sessionActive={Boolean(state.session)}
        onClose={() => setSettingsOpen(false)}
        onChange={setSettings}
      />

      <SubagentModal
        open={subagentOpen}
        confirmLoading={Boolean(subagentOperationKey && state.operations[subagentOperationKey])}
        subagentTargets={subagentTargets}
        onClose={() => setSubagentOpen(false)}
        onStart={async (agentName, description) => {
          await actions.startSubagent(agentName, description);
          openTaskCenterTab('subagents');
        }}
      />
    </AgentWorkbenchShell>
  );
}
