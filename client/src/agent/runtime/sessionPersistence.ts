import type { RecentAgentSession } from './agentRuntime';
import type { AgentSession } from '../../services/api';

const STORAGE_KEY = 'finetune.agent-workbench.sessions.v1';

interface PersistedAgentRuntime {
  version: 1;
  activeSessionId: string | null;
  sessions: RecentAgentSession[];
}

const EMPTY_RUNTIME: PersistedAgentRuntime = {
  version: 1,
  activeSessionId: null,
  sessions: [],
};

export function readPersistedAgentRuntime(storage: Pick<Storage, 'getItem'> = localStorage): PersistedAgentRuntime {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY_RUNTIME;
    const parsed = JSON.parse(raw) as Partial<PersistedAgentRuntime>;
    if (parsed.version !== 1 || !Array.isArray(parsed.sessions)) return EMPTY_RUNTIME;
    const sessions = parsed.sessions
      .filter((session): session is RecentAgentSession => (
        Boolean(session)
        && typeof session.id === 'string'
        && typeof session.title === 'string'
        && typeof session.status === 'string'
      ))
      .map((session) => ({
        ...session,
        taskMode: ['build', 'train', 'hybrid'].includes(String(session.taskMode))
          ? session.taskMode
          : undefined,
        displayTitle: session.displayTitle || session.title,
        preferences: session.preferences || {
          display_title: null,
          pinned: false,
          archived: false,
          updated_at: null,
        },
      }))
      .slice(0, 20);
    return {
      version: 1,
      activeSessionId: typeof parsed.activeSessionId === 'string' ? parsed.activeSessionId : null,
      sessions,
    };
  } catch {
    return EMPTY_RUNTIME;
  }
}

export function persistAgentRuntime(
  value: Omit<PersistedAgentRuntime, 'version'>,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, ...value }));
  } catch {
    // Storage can be unavailable or full. The server-side session index remains authoritative.
  }
}

/** Make a server-created continuation the active Workbench task before navigation. */
export function activatePersistedAgentSession(
  session: AgentSession,
  storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage,
): void {
  const current = readPersistedAgentRuntime(storage);
  const preferences = session.preferences || {
    display_title: null,
    pinned: false,
    archived: false,
    updated_at: null,
  };
  const recent: RecentAgentSession = {
    id: session.id,
    title: session.title || '未命名任务',
    displayTitle: preferences.display_title || session.title || '未命名任务',
    status: session.status,
    agentId: session.agent_id,
    projectPath: session.project_path,
    taskMode: session.task_mode,
    updatedAt: session.updated_at,
    preferences,
  };
  persistAgentRuntime(
    {
      activeSessionId: session.id,
      sessions: [recent, ...current.sessions.filter((item) => item.id !== session.id)].slice(0, 20),
    },
    storage,
  );
}
