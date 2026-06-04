import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AgentWorkspace } from '../../services/api';

export type AgentWorkspaceSelection =
  | { type: 'run'; sessionId: string }
  | { type: 'timeline_item'; itemId: string; partId?: string }
  | { type: 'async_task'; taskId: string; childSessionId?: string; expandDetail?: boolean }
  | { type: 'permission'; permissionPartId: string }
  | { type: 'artifact'; artifactId: string }
  | { type: 'file'; path: string }
  | { type: 'command'; partId: string };

export interface UseAgentWorkspaceSelectionResult {
  selection: AgentWorkspaceSelection | null;
  selectRun: () => void;
  selectTimelineItem: (itemId: string, partId?: string) => void;
  selectAsyncTask: (taskId: string, childSessionId?: string, options?: { expandDetail?: boolean }) => void;
  selectPermission: (permissionPartId: string) => void;
  selectArtifact: (artifactId: string) => void;
  selectFile: (path: string) => void;
  selectCommand: (partId: string) => void;
}

export function useAgentWorkspaceSelection(
  workspace: AgentWorkspace | null,
): UseAgentWorkspaceSelectionResult {
  const sessionId = workspace?.session.id || '';
  const [selection, setSelection] = useState<AgentWorkspaceSelection | null>(null);
  const lastSessionIdRef = useRef('');

  useEffect(() => {
    if (!sessionId) {
      setSelection(null);
      lastSessionIdRef.current = '';
      return;
    }
    if (lastSessionIdRef.current !== sessionId) {
      lastSessionIdRef.current = sessionId;
      setSelection({ type: 'run', sessionId });
      return;
    }
    setSelection((current) => current || { type: 'run', sessionId });
  }, [sessionId]);

  const selectRun = useCallback(() => {
    if (sessionId) setSelection({ type: 'run', sessionId });
  }, [sessionId]);

  const selectTimelineItem = useCallback((itemId: string, partId?: string) => {
    setSelection({ type: 'timeline_item', itemId, partId });
  }, []);

  const selectAsyncTask = useCallback((taskId: string, childSessionId?: string, options?: { expandDetail?: boolean }) => {
    setSelection({ type: 'async_task', taskId, childSessionId, expandDetail: options?.expandDetail });
  }, []);

  const selectPermission = useCallback((permissionPartId: string) => {
    setSelection({ type: 'permission', permissionPartId });
  }, []);

  const selectArtifact = useCallback((artifactId: string) => {
    setSelection({ type: 'artifact', artifactId });
  }, []);

  const selectFile = useCallback((path: string) => {
    setSelection({ type: 'file', path });
  }, []);

  const selectCommand = useCallback((partId: string) => {
    setSelection({ type: 'command', partId });
  }, []);

  return useMemo(() => ({
    selection,
    selectRun,
    selectTimelineItem,
    selectAsyncTask,
    selectPermission,
    selectArtifact,
    selectFile,
    selectCommand,
  }), [selectArtifact, selectAsyncTask, selectCommand, selectFile, selectPermission, selectRun, selectTimelineItem, selection]);
}
