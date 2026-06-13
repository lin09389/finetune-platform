import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useAgentWorkspaceSelection } from '../hooks/chat/useAgentWorkspaceSelection';
import type { AgentWorkspace } from '../services/api';

function workspace(id = 'ags_parent'): AgentWorkspace {
  return {
    session: {
      id,
      agent_id: 'build',
      status: 'running',
      title: 'Build',
      metadata: {},
      parts: [],
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    },
    status_text: {},
    timeline: [],
    pending_permission: null,
    diagnostics: {},
    async_tasks: {
      tasks: [],
      metrics: {
        total: 0,
        by_status: {},
        running: 0,
        failed: 0,
        cancelled: 0,
        completed: 0,
        attention: 0,
        recovery_count: 0,
        event_count: 0,
        last_event: null,
      },
    },
    artifacts: [],
    changed_files: [],
    next_actions: [],
    recent_events: [],
  };
}

describe('useAgentWorkspaceSelection', () => {
  it('defaults to run selection and supports next-action targets', async () => {
    const { result, rerender } = renderHook(
      ({ value }) => useAgentWorkspaceSelection(value),
      { initialProps: { value: workspace() } },
    );

    await waitFor(() => expect(result.current.selection).toEqual({ type: 'run', sessionId: 'ags_parent' }));

    act(() => result.current.selectArtifact('risks_1'));
    expect(result.current.selection).toEqual({ type: 'artifact', artifactId: 'risks_1' });

    act(() => result.current.selectFile('/workspace/app.py'));
    expect(result.current.selection).toEqual({ type: 'file', path: '/workspace/app.py' });

    act(() => result.current.selectPermission('perm_1'));
    expect(result.current.selection).toEqual({ type: 'permission', permissionPartId: 'perm_1' });

    rerender({ value: workspace('ags_next') });
    await waitFor(() => expect(result.current.selection).toEqual({ type: 'run', sessionId: 'ags_next' }));
  });
});
