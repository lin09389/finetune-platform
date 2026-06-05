import { useCallback } from 'react';
import type { AgentWorkspaceNextAction } from '../../services/api';
import type { UseAgentWorkspaceResult } from './useAgentWorkspace';
import type { UseAgentWorkspaceSelectionResult } from './useAgentWorkspaceSelection';

interface UseAgentWorkspaceNextActionRouterOptions {
  agentWorkspace: UseAgentWorkspaceResult;
  workspaceSelection: UseAgentWorkspaceSelectionResult;
  openInspector: () => void;
  openWorkbenchTab?: (tab: string) => void;
}

export function useAgentWorkspaceNextActionRouter({
  agentWorkspace,
  workspaceSelection,
  openInspector,
  openWorkbenchTab,
}: UseAgentWorkspaceNextActionRouterOptions) {
  return useCallback(async (action: AgentWorkspaceNextAction) => {
    openInspector();

    if (action.action_type === 'start_review' || action.action_type === 'start_explore') {
      await agentWorkspace.runNextAction(action);
      return;
    }

    if (action.action_type === 'resolve_permission') {
      openWorkbenchTab?.('approvals');
      const permissionPartId = String(action.payload?.permission_part_id || '');
      const taskId = String(action.payload?.task_id || action.source_task_id || '');
      if (permissionPartId) {
        workspaceSelection.selectPermission(permissionPartId);
      } else if (taskId) {
        selectTask(taskId, action, workspaceSelection);
      } else {
        workspaceSelection.selectRun();
      }
      return;
    }

    if (action.action_type === 'review_risks' && action.source_artifact_id) {
      openWorkbenchTab?.('artifacts');
      workspaceSelection.selectArtifact(action.source_artifact_id);
      return;
    }

    if (action.action_type === 'inspect_file' && action.payload?.path) {
      openWorkbenchTab?.('files');
      workspaceSelection.selectFile(String(action.payload.path));
      return;
    }

    if (action.action_type === 'restart_failed_task') {
      openWorkbenchTab?.('subagents');
      const taskId = String(action.payload?.task_id || action.source_task_id || '');
      if (taskId) {
        selectTask(taskId, action, workspaceSelection);
      }
      return;
    }

    workspaceSelection.selectRun();
  }, [agentWorkspace, openInspector, openWorkbenchTab, workspaceSelection]);
}

function selectTask(
  taskId: string,
  action: AgentWorkspaceNextAction,
  workspaceSelection: UseAgentWorkspaceSelectionResult,
) {
  const childSessionId = action.payload?.child_session_id ? String(action.payload.child_session_id) : undefined;
  workspaceSelection.selectAsyncTask(taskId, childSessionId, { expandDetail: true });
}
