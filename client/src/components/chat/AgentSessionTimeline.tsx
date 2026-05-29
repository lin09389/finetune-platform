import type { AgentPart, AgentSession, AgentSessionUiTimelineItem } from '../../services/api';
import type { ChatAgentMetadata } from '../../types';
import AgentPartMessage from './AgentPartMessage';

interface AgentSessionTimelineProps {
  session: AgentSession;
  items?: AgentSessionUiTimelineItem[];
  onRefreshRun?: (runId: string) => void | Promise<void>;
}

function partFromItem(session: AgentSession, item: AgentSessionUiTimelineItem): AgentPart {
  const existing = session.parts.find((part) => part.id === (item.part_id || item.id));
  return existing || {
    id: item.part_id || item.id,
    session_id: item.session_id || session.id,
    type: item.type as AgentPart['type'],
    status: item.status as AgentPart['status'],
    title: item.title,
    content: item.content,
    payload: item.payload || {},
    created_at: item.created_at || session.created_at,
    updated_at: item.updated_at || session.updated_at,
  };
}

export default function AgentSessionTimeline({ session, items, onRefreshRun }: AgentSessionTimelineProps) {
  const timeline = items || session.metadata?.ui_state?.timeline || [];
  return (
    <>
      {timeline.map((item) => {
        const part = partFromItem(session, item);
        const metadata: ChatAgentMetadata = {
          agent_run_id: session.id,
          agent_session_id: session.id,
          agent_part_id: part.id,
          kind: 'agent_part',
          status: part.status || session.status,
          can_approve: false,
          can_execute: false,
          ui_state: session.metadata?.ui_state,
          ui_item: item,
          agent_part: part,
          agent_parts: session.parts,
          agent_session_state: session.metadata?.state,
          agent_session_diagnostics: session.metadata?.diagnostics,
          agent_streaming_diagnostics: session.metadata?.streaming_diagnostics,
          active_agent_id: session.agent_id,
        };
        return (
          <AgentPartMessage
            key={item.id}
            content={part.content || part.title || ''}
            metadata={metadata}
            onRefreshRun={onRefreshRun}
          />
        );
      })}
    </>
  );
}
