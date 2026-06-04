import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useAgentWorkspaceNextActionRouter } from '../hooks/chat/useAgentWorkspaceNextActionRouter';
import type { UseAgentWorkspaceResult } from '../hooks/chat/useAgentWorkspace';
import type { UseAgentWorkspaceSelectionResult } from '../hooks/chat/useAgentWorkspaceSelection';
import type { AgentWorkspaceNextAction } from '../services/api';

const workspace = {
  runNextAction: vi.fn(),
} as unknown as UseAgentWorkspaceResult;

function selection(): UseAgentWorkspaceSelectionResult {
  return {
    selection: null,
    selectRun: vi.fn(),
    selectTimelineItem: vi.fn(),
    selectAsyncTask: vi.fn(),
    selectPermission: vi.fn(),
    selectArtifact: vi.fn(),
    selectFile: vi.fn(),
    selectCommand: vi.fn(),
  };
}

function action(type: AgentWorkspaceNextAction['action_type'], payload: Record<string, any> = {}): AgentWorkspaceNextAction {
  return {
    id: `${type}:1`,
    action_type: type,
    title: type,
    summary: '',
    priority: 'medium',
    payload,
    source_artifact_id: payload.artifact_id,
    source_task_id: payload.task_id,
  };
}

describe('useAgentWorkspaceNextActionRouter', () => {
  it('starts safe subtask actions through the workspace hook', async () => {
    const currentSelection = selection();
    const openInspector = vi.fn();
    const { result } = renderHook(() => useAgentWorkspaceNextActionRouter({
      agentWorkspace: workspace,
      workspaceSelection: currentSelection,
      openInspector,
    }));

    await act(async () => {
      await result.current(action('start_review', { subagent_type: 'review', description: 'review' }));
    });

    expect(openInspector).toHaveBeenCalled();
    expect(workspace.runNextAction).toHaveBeenCalledWith(expect.objectContaining({ action_type: 'start_review' }));
  });

  it('routes display actions to workspace selection', async () => {
    const currentSelection = selection();
    const { result } = renderHook(() => useAgentWorkspaceNextActionRouter({
      agentWorkspace: workspace,
      workspaceSelection: currentSelection,
      openInspector: vi.fn(),
    }));

    await act(async () => {
      await result.current(action('resolve_permission', { permission_part_id: 'perm_1' }));
      await result.current(action('review_risks', { artifact_id: 'risks_1' }));
      await result.current(action('inspect_file', { path: '/workspace/app.py' }));
      await result.current(action('restart_failed_task', { task_id: 'task_1', child_session_id: 'child_1' }));
    });

    expect(currentSelection.selectPermission).toHaveBeenCalledWith('perm_1');
    expect(currentSelection.selectArtifact).toHaveBeenCalledWith('risks_1');
    expect(currentSelection.selectFile).toHaveBeenCalledWith('/workspace/app.py');
    expect(currentSelection.selectAsyncTask).toHaveBeenCalledWith('task_1', 'child_1', { expandDetail: true });
  });
});
