import type { AgentRuntimePersistence } from '../runtime/useAgentWorkbench';
import type { AgentTransport } from '../transport/agentTransport';
import AgentWorkbenchPage from './AgentWorkbenchPage';

export interface AgentWorkbenchRouteProps {
  transport?: AgentTransport;
  persistence?: AgentRuntimePersistence;
}

export default function AgentWorkbenchRoute({
  transport,
  persistence,
}: AgentWorkbenchRouteProps) {
  return <AgentWorkbenchPage transport={transport} persistence={persistence} />;
}
