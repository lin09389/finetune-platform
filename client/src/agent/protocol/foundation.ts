export const AGENT_PROTOCOL_BASELINE_VERSION = 'agent-frontend-baseline.v1' as const;

export const REQUIRED_STREAM_ENVELOPE_FIELDS = [
  'id',
  'session_id',
  'event_type',
  'chunk_type',
  'message',
  'payload',
  'created_at',
] as const;

export interface AgentProtocolBaselineFixture {
  fixture_version: typeof AGENT_PROTOCOL_BASELINE_VERSION;
  source: {
    backend_contract: string;
    captured_from: string[];
    sanitized: true;
  };
  snapshot: Record<string, unknown>;
  events: Array<Record<string, unknown>>;
}
