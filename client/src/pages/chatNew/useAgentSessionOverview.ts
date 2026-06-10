import { useEffect, useMemo, useState } from 'react';

import { getAgentSessionOverview } from '../../services/api';
import type { AgentPart, AgentSessionOverview } from '../../services/api';

export function useAgentSessionOverview(params: {
  sessionId?: string;
  parts: AgentPart[];
  status: string;
}) {
  const { sessionId, parts, status } = params;
  const [overview, setOverview] = useState<AgentSessionOverview | null>(null);

  const partsSignature = useMemo(
    () => parts.map((part) => `${part.id}:${part.status}:${part.updated_at || ''}`).join(','),
    [parts],
  );

  useEffect(() => {
    if (!sessionId) {
      setOverview(null);
      return;
    }
    let cancelled = false;
    getAgentSessionOverview(sessionId)
      .then((nextOverview) => {
        if (!cancelled) setOverview(nextOverview);
      })
      .catch(() => {
        if (!cancelled) setOverview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, partsSignature, status]);

  return overview;
}
