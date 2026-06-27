import {
  ReloadOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { Button, Drawer, Form, Input, Modal, Select, Tooltip } from 'antd';
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import type { AgentHitlDecision } from '../../services/api';
import { useOptionalRuntimeContext } from '../../runtime/RuntimeContext';
import AgentAttentionRail from '../components/AgentAttentionRail';
import AgentEnvironmentRail from '../components/AgentEnvironmentRail';
import AgentRunTimeline from '../components/AgentRunTimeline';
import AgentSessionRail from '../components/AgentSessionRail';
import AgentTaskComposer from '../components/AgentTaskComposer';
import AgentWorkspaceView, {
  workspaceTabs,
  type AgentWorkspaceTab,
} from '../components/AgentWorkspaceView';
import {
  persistAgentWorkbenchSettings,
  readAgentWorkbenchSettings,
  type AgentWorkbenchSettings,
} from '../config/workbenchSettings';
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
const ACTIVE_TAB_KEY = 'finetune.agent.active-tab.v1';

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
  const [activeTab, setActiveTab] = useState<AgentWorkspaceTab>(() => {
    const stored = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(ACTIVE_TAB_KEY);
    return workspaceTabs.some((tab) => tab.key === stored) ? stored as AgentWorkspaceTab : 'activity';
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [subagentOpen, setSubagentOpen] = useState(false);
  const [requestedFilePath, setRequestedFilePath] = useState<string | null>(null);
  const [attentionOpenRequest, setAttentionOpenRequest] = useState(0);
  const [settings, setSettings] = useState<AgentWorkbenchSettings>(readAgentWorkbenchSettings);
  const [subagentForm] = Form.useForm<{ agentName: string; description: string }>();
  const timeline = useMemo(() => selectTimeline(state), [state]);
  const connectionLabel = selectConnectionLabel(state);
  const statusLabel = selectWorkspaceStatus(state);
  const projectLabel = selectWorkspaceProjectLabel(state.workspace);
  const attentionCount = selectAttentionCount(state);
  const activeOperation = state.activeOperation;
  const composerOperation = Object.values(state.operations).find((operation) => (
    operation.key.startsWith('submit:') || operation.key.startsWith('interrupt:')
  ));
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
    sessionStorage.setItem(ACTIVE_TAB_KEY, activeTab);
  }, [activeTab]);

  useEffect(() => {
    const switchWorkspaceTab = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey) return;
      const index = Number(event.key) - 1;
      const tab = workspaceTabs[index];
      if (!tab) return;
      event.preventDefault();
      setActiveTab(tab.key);
    };
    window.addEventListener('keydown', switchWorkspaceTab);
    return () => window.removeEventListener('keydown', switchWorkspaceTab);
  }, []);

  const decidePermission = (partId: string, decisions: AgentHitlDecision[]) => {
    void actions.decidePermission(partId, decisions);
  };

  const sessionRail = (embedded = false) => (
    <AgentSessionRail
      embedded={embedded}
      sessions={state.recentSessions}
      activeSessionId={state.activeSessionId}
      onNew={() => {
        actions.newSession();
        setActiveTab('activity');
      }}
      onSelect={(sessionId) => {
        actions.selectSession(sessionId);
        setActiveTab('activity');
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

  return (
    <AgentWorkbenchShell
      title={state.session?.title || '新任务'}
      subtitle={`${projectLabel} · ${statusLabel} · ${agentRuntimeLabel}`}
      connection={state.connection}
      connectionLabel={connectionLabel}
      attentionCount={attentionCount}
      attentionOpenRequest={attentionOpenRequest}
      desktopSessionRail={sessionRail()}
      mobileSessionRail={sessionRail(true)}
      desktopEnvironmentRail={environmentRail}
      mobileAttentionRail={attentionRail(true)}
      toolbar={toolbar}
    >
      <main className={styles.mainSurface}>
        <div className={styles.contentSurface}>
          {activeTab === 'activity' ? (
            <AgentRunTimeline
              timeline={timeline}
              pendingLabel={composerOperation?.key.startsWith('submit:') ? composerOperation.label : undefined}
              errorMessage={state.error}
            />
          ) : activeTab === 'terminal' ? (
            <Suspense fallback={<div className={styles.panelLoading}>正在加载终端...</div>}>
              <AgentTerminalPanel timeline={timeline} />
            </Suspense>
          ) : (
            <AgentWorkspaceView
              tab={activeTab}
              workspace={state.workspace}
              busyKey={activeOperation?.key}
              requestedFilePath={requestedFilePath}
              onRecover={(node) => void actions.recoverNode(node)}
              onCancelSubagent={(taskId) => void actions.cancelSubagent(taskId)}
              onRunNextAction={(action) => {
                const intent = routeAgentNextAction(
                  action,
                  state.workspace?.async_tasks.tasks || [],
                );
                switch (intent.type) {
                  case 'start_subagent':
                    void actions.startSubagent(
                      intent.agentName,
                      intent.description,
                    );
                    setActiveTab('subagents');
                    break;
                  case 'open_attention':
                    setActiveTab('activity');
                    setAttentionOpenRequest((current) => current + 1);
                    break;
                  case 'open_tab':
                    if (intent.filePath) setRequestedFilePath(intent.filePath);
                    setActiveTab(intent.tab);
                    break;
                  case 'submit_prompt':
                    void actions.submitTask({
                      content: intent.content,
                      agentId: state.session?.agent_id || 'build',
                      provider: effectiveAgentProvider,
                      model: effectiveAgentModel,
                    });
                    setActiveTab('activity');
                    break;
                }
              }}
            />
          )}
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
        <nav className={styles.workspaceTabs} aria-label="工作区面板">
          {workspaceTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={activeTab === tab.key ? styles.activeTab : undefined}
              aria-current={activeTab === tab.key ? 'page' : undefined}
              aria-label={`${tab.label}面板`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.icon}
              <span>{tab.label}</span>
              {tab.key === 'subagents' && state.workspace?.async_tasks.metrics.attention ? (
                <span className={styles.tabCount}>{state.workspace.async_tasks.metrics.attention}</span>
              ) : null}
            </button>
          ))}
        </nav>
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
            await actions.startSubagent(values.agentName, values.description);
            subagentForm.resetFields();
            setSubagentOpen(false);
            setActiveTab('subagents');
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
