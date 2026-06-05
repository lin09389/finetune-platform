import React from 'react';
import type { AgentHitlDecision, AgentWorkspaceNextAction } from '../../services/api';
import type { UseAgentAsyncTasksResult } from '../../hooks/chat/useAgentAsyncTasks';
import type { UseAgentWorkspaceResult } from '../../hooks/chat/useAgentWorkspace';
import type { UseAgentWorkspaceSelectionResult } from '../../hooks/chat/useAgentWorkspaceSelection';
import AgentAsyncTasksPanel from './AgentAsyncTasksPanel';
import AgentArtifactLedger from './AgentArtifactLedger';
import AgentInspector from './AgentInspector';
import AgentPlanPanel from './AgentPlanPanel';
import AgentRuntimePanel from './AgentRuntimePanel';
import AgentWorkbenchPanel, { WorkbenchEmpty } from './AgentWorkbenchPanel';

interface AgentWorkspaceContainerProps {
  activeKey: string;
  onActiveKeyChange: (key: string) => void;
  changedFiles: number;
  runContent: React.ReactNode;
  configContent: React.ReactNode;
  progressContent: React.ReactNode;
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
  fileTreeContent,
  agentWorkspace,
  asyncTasks,
  workspaceSelection,
  sessionId,
  onSubmitPermission,
  onOpenFile,
  onRunNextAction,
}: AgentWorkspaceContainerProps) {
  return (
    <AgentWorkbenchPanel
      activeKey={activeKey}
      onActiveKeyChange={onActiveKeyChange}
      changedFiles={changedFiles}
      runContent={runContent}
      configContent={configContent}
      progressContent={progressContent}
      planContent={<AgentPlanPanel plan={agentWorkspace.workspace?.plan ?? null} />}
      artifactLedgerContent={(
        <AgentArtifactLedger
          artifacts={agentWorkspace.workspace?.artifacts ?? []}
          onSelectArtifact={workspaceSelection.selectArtifact}
          onOpenFile={onOpenFile}
        />
      )}
      approvalsContent={agentWorkspace.workspace?.pending_permission ? (
        <AgentInspector
          workspace={agentWorkspace.workspace}
          selection={{ type: 'permission', permissionPartId: agentWorkspace.workspace.pending_permission.part_id }}
          onSubmitPermission={onSubmitPermission}
          onRefresh={agentWorkspace.refresh}
          onOpenFile={onOpenFile}
          onRunNextAction={onRunNextAction}
        />
      ) : (
        <WorkbenchEmpty description="暂无待确认动作。" />
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
