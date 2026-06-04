import { useCallback, useEffect, useMemo, useState } from 'react';
import type { AgentAsyncTask, AgentAsyncTaskMetrics } from '../../services/api';
import type { UseAgentWorkspaceResult } from './useAgentWorkspace';

interface UseAgentAsyncTasksOptions {
  pollIntervalMs?: number;
}

export interface UseAgentAsyncTasksResult {
  tasks: AgentAsyncTask[];
  metrics: AgentAsyncTaskMetrics | null;
  loading: boolean;
  statusFilter: string;
  focusedTaskId: string | null;
  expandedTaskId: string | null;
  setStatusFilter: (filter: string) => void;
  focusTask: (taskId?: string | null) => void;
  expandTask: (taskId?: string | null) => void;
  refresh: () => Promise<void>;
  startTask: (payload: { subagent_type: string; description: string }) => Promise<void>;
  cancelTask: (taskId: string, payload?: { reason?: string }) => Promise<void>;
  restartTask: (taskId: string, payload: { description: string }) => Promise<void>;
}

export function useAgentAsyncTasks(
  agentWorkspace: UseAgentWorkspaceResult,
  options: UseAgentAsyncTasksOptions = {},
): UseAgentAsyncTasksResult {
  const pollIntervalMs = options.pollIntervalMs ?? 3000;
  const [statusFilter, setStatusFilter] = useState('all');
  const [focusedTaskId, setFocusedTaskId] = useState<string | null>(null);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const sessionId = agentWorkspace.workspace?.session.id ?? null;
  const allTasks = agentWorkspace.workspace?.async_tasks.tasks ?? [];
  const metrics: AgentAsyncTaskMetrics | null = agentWorkspace.workspace?.async_tasks.metrics ?? null;

  const tasks = useMemo(
    () => statusFilter === 'all' ? allTasks : allTasks.filter((task) => task.status === statusFilter),
    [allTasks, statusFilter],
  );

  const hasActiveTask = useMemo(
    () => (
      (metrics?.running ?? 0) > 0 ||
      (metrics?.by_status?.pending ?? 0) > 0 ||
      tasks.some((task) => task.status === 'pending' || task.status === 'running')
    ),
    [metrics?.by_status?.pending, metrics?.running, tasks],
  );

  const refresh = agentWorkspace.refresh;

  useEffect(() => {
    if (!sessionId || !hasActiveTask) return undefined;
    const interval = window.setInterval(() => {
      void refresh();
    }, pollIntervalMs);
    return () => window.clearInterval(interval);
  }, [hasActiveTask, pollIntervalMs, refresh, sessionId]);

  const startTask = useCallback(async (payload: { subagent_type: string; description: string }) => {
    await agentWorkspace.startTask(payload);
  }, [agentWorkspace]);

  const cancelTask = useCallback(async (taskId: string, payload?: { reason?: string }) => {
    await agentWorkspace.cancelTask(taskId, payload);
  }, [agentWorkspace]);

  const restartTask = useCallback(async (taskId: string, payload: { description: string }) => {
    await agentWorkspace.restartTask(taskId, payload);
  }, [agentWorkspace]);

  const focusTask = useCallback((taskId?: string | null) => {
    setFocusedTaskId(taskId || null);
  }, []);

  const expandTask = useCallback((taskId?: string | null) => {
    setExpandedTaskId(taskId || null);
  }, []);

  return {
    tasks,
    metrics,
    loading: agentWorkspace.loading,
    statusFilter,
    focusedTaskId,
    expandedTaskId,
    setStatusFilter,
    focusTask,
    expandTask,
    refresh,
    startTask,
    cancelTask,
    restartTask,
  };
}
