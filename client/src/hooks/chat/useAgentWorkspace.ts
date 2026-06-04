import { useCallback, useEffect, useRef, useState } from 'react';
import {
  cancelAgentAsyncTask,
  getAgentWorkspace,
  startAgentAsyncTask,
  updateAgentAsyncTask,
  type AgentWorkspaceNextAction,
  type AgentWorkspace,
} from '../../services/api';

export interface UseAgentWorkspaceResult {
  workspace: AgentWorkspace | null;
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
  startTask: (payload: { subagent_type: string; description: string }) => Promise<void>;
  cancelTask: (taskId: string, payload?: { reason?: string }) => Promise<void>;
  restartTask: (taskId: string, payload: { description: string }) => Promise<void>;
  runNextAction: (action: AgentWorkspaceNextAction) => Promise<void>;
}

export function useAgentWorkspace(sessionId?: string | null): UseAgentWorkspaceResult {
  const [workspace, setWorkspace] = useState<AgentWorkspace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const requestSeqRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;

    if (!sessionId) {
      setWorkspace(null);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    try {
      const nextWorkspace = await getAgentWorkspace(sessionId);
      if (requestSeqRef.current !== requestSeq) return;
      setWorkspace(nextWorkspace);
      setError(null);
    } catch (err) {
      if (requestSeqRef.current !== requestSeq) return;
      setError(err instanceof Error ? err : new Error('Agent workspace 加载失败'));
    } finally {
      if (requestSeqRef.current === requestSeq) {
        setLoading(false);
      }
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const startTask = useCallback(async (payload: { subagent_type: string; description: string }) => {
    if (!sessionId) return;
    await startAgentAsyncTask(sessionId, payload);
    await refresh();
  }, [refresh, sessionId]);

  const cancelTask = useCallback(async (taskId: string, payload?: { reason?: string }) => {
    if (!sessionId) return;
    await cancelAgentAsyncTask(sessionId, taskId, payload);
    await refresh();
  }, [refresh, sessionId]);

  const restartTask = useCallback(async (taskId: string, payload: { description: string }) => {
    if (!sessionId) return;
    await updateAgentAsyncTask(sessionId, taskId, payload);
    await refresh();
  }, [refresh, sessionId]);

  const runNextAction = useCallback(async (action: AgentWorkspaceNextAction) => {
    if (action.action_type !== 'start_review' && action.action_type !== 'start_explore') {
      return;
    }
    const subagentType = String(action.payload?.subagent_type || (action.action_type === 'start_review' ? 'review' : 'explore'));
    const description = String(action.payload?.description || action.summary || action.title);
    await startTask({ subagent_type: subagentType, description });
  }, [startTask]);

  return {
    workspace,
    loading,
    error,
    refresh,
    startTask,
    cancelTask,
    restartTask,
    runNextAction,
  };
}
