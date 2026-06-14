import React from 'react';
import { message } from 'antd';
import { recoverAgentExecutionPlanNode } from '../../services/api';
import type { AgentExecutionPlanNode, AgentHitlDecision, AgentWorkspaceNextAction } from '../../services/api';
import type { UseAgentAsyncTasksResult } from '../../hooks/chat/useAgentAsyncTasks';
import type { UseAgentWorkspaceResult } from '../../hooks/chat/useAgentWorkspace';
import type { UseAgentWorkspaceSelectionResult } from '../../hooks/chat/useAgentWorkspaceSelection';
import AgentApprovalInbox from './AgentApprovalInbox';
import AgentAsyncTasksPanel from './AgentAsyncTasksPanel';
import AgentArtifactLedger from './AgentArtifactLedger';
import AgentExecutionTimeline from './AgentExecutionTimeline';
import AgentInspector from './AgentInspector';
import AgentOrchestrationPanel from './AgentOrchestrationPanel';
import AgentRuntimePanel from './AgentRuntimePanel';
import AgentWorkbenchPanel, { WorkbenchEmpty } from './AgentWorkbenchPanel';
import styles from './AgentWorkspacePanels.module.css';

interface AgentWorkspaceContainerProps {
  activeKey: string;
  onActiveKeyChange: (key: string) => void;
  changedFiles: number;
  runContent: React.ReactNode;
  configContent: React.ReactNode;
  progressContent: React.ReactNode;
  outputContent?: React.ReactNode;
  fileTreeContent: React.ReactNode;
  agentWorkspace: UseAgentWorkspaceResult;
  asyncTasks: UseAgentAsyncTasksResult;
  workspaceSelection: UseAgentWorkspaceSelectionResult;
  sessionId?: string | null;
  onSubmitPermission: (permissionId: string, decisions: AgentHitlDecision[]) => void | Promise<void>;
  onOpenFile: (path: string) => void | Promise<void>;
  onRunNextAction: (action: AgentWorkspaceNextAction) => void | Promise<void>;
}

export default function AgentWorkspaceContainer({
  activeKey,
  onActiveKeyChange,
  changedFiles,
  runContent,
  configContent,
  progressContent,
  outputContent,
  fileTreeContent,
  agentWorkspace,
  asyncTasks,
  workspaceSelection,
  sessionId,
  onSubmitPermission,
  onOpenFile,
  onRunNextAction,
}: AgentWorkspaceContainerProps) {
  const selectTask = (taskId: string) => {
    const task = agentWorkspace.workspace?.async_tasks.tasks.find((item) => item.task_id === taskId);
    workspaceSelection.selectAsyncTask(taskId, task?.child_session_id || undefined);
    onActiveKeyChange('subagents');
  };
  const selectArtifact = (artifactId: string) => {
    workspaceSelection.selectArtifact(artifactId);
    onActiveKeyChange('artifacts');
  };
  const selectExecutionPart = (partId: string) => {
    workspaceSelection.selectTimelineItem(`exec:${partId}`, partId);
    onActiveKeyChange('execution');
  };
  const recoverNode = async (node: AgentExecutionPlanNode, action?: string | null) => {
    if (!sessionId) return;
    try {
      await recoverAgentExecutionPlanNode(sessionId, node.id, { action });
      message.success(action === 'restart_subagent' ? '子任务恢复已启动' : '节点恢复已启动');
      await agentWorkspace.refresh();
      await asyncTasks.refresh();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '节点恢复失败');
      throw error;
    }
  };

  return (
    <AgentWorkbenchPanel
      activeKey={activeKey}
      onActiveKeyChange={onActiveKeyChange}
      changedFiles={changedFiles}
      runContent={runContent}
      configContent={configContent}
      progressContent={progressContent}
      planContent={(
        <AgentOrchestrationPanel
          executionPlan={agentWorkspace.workspace?.execution_plan ?? agentWorkspace.workspace?.runtime?.execution_plan ?? null}
          runtimePolicy={agentWorkspace.workspace?.runtime_policy ?? agentWorkspace.workspace?.runtime?.policy ?? null}
          resourceProfile={agentWorkspace.workspace?.resource_profile ?? agentWorkspace.workspace?.runtime?.resource_profile ?? null}
          asyncTasks={agentWorkspace.workspace?.async_tasks.tasks ?? []}
          onSelectTask={selectTask}
          onRecoverNode={recoverNode}
        />
      )}
      artifactLedgerContent={(
        <div className={styles.splitPanel}>
          <div style={{ display: 'grid', gap: 12, minWidth: 0 }}>
            {outputContent}
            <AgentArtifactLedger
              artifacts={agentWorkspace.workspace?.artifacts ?? []}
              onSelectArtifact={selectArtifact}
              onOpenFile={onOpenFile}
              onSelectSourcePart={selectExecutionPart}
              onSelectSourceTask={selectTask}
            />
          </div>
          <AgentInspector
            workspace={agentWorkspace.workspace}
            selection={workspaceSelection.selection}
            onSubmitPermission={onSubmitPermission}
            onRefresh={agentWorkspace.refresh}
            onOpenFile={onOpenFile}
            onRunNextAction={onRunNextAction}
          />
        </div>
      )}
      approvalsContent={(
        <AgentApprovalInbox
          workspace={agentWorkspace.workspace}
          onSubmitPermission={onSubmitPermission}
          onRefresh={agentWorkspace.refresh}
          onSelectAsyncTask={selectTask}
        />
      )}
      executionContent={(
        <div className={styles.splitPanel}>
          <AgentExecutionTimeline
            items={agentWorkspace.workspace?.execution_timeline ?? []}
            onSelectItem={(item) => selectExecutionPart(item.source_part_id)}
          />
          <AgentInspector
            workspace={agentWorkspace.workspace}
            selection={workspaceSelection.selection}
            onSubmitPermission={onSubmitPermission}
            onRefresh={agentWorkspace.refresh}
            onOpenFile={onOpenFile}
            onRunNextAction={onRunNextAction}
          />
        </div>
      )}
      runtimeContent={<AgentRuntimePanel runtime={agentWorkspace.workspace?.runtime ?? null} sessionId={sessionId} />}
      inspectorContent={(
        <AgentInspector
          workspace={agentWorkspace.workspace}
          selection={workspaceSelection.selection}
          onSubmitPermission={onSubmitPermission}
          onRefresh={agentWorkspace.refresh}
          onOpenFile={onOpenFile}
          onRunNextAction={onRunNextAction}
        />
      )}
      asyncTasksContent={(
        <AgentAsyncTasksPanel
          sessionId={sessionId}
          tasks={asyncTasks.tasks}
          metrics={asyncTasks.metrics}
          loading={asyncTasks.loading}
          statusFilter={asyncTasks.statusFilter}
          focusedTaskId={asyncTasks.focusedTaskId}
          expandedTaskId={asyncTasks.expandedTaskId}
          onStatusFilterChange={asyncTasks.setStatusFilter}
          onExpandedTaskChange={asyncTasks.expandTask}
          onRefresh={asyncTasks.refresh}
          onStartTask={asyncTasks.startTask}
          onCancelTask={asyncTasks.cancelTask}
          onRestartTask={asyncTasks.restartTask}
        />
      )}
      fileTreeContent={fileTreeContent}
      editorContent={<WorkbenchEmpty description="主编辑器已提升到中央 Agent IDE 工作区。" />}
    />
  );
}
