import { useEffect, useMemo, useRef, useState } from 'react';
import type { TrainingEventV2 } from '../../services/api';
import { subscribeTrainingEventsV2 } from '../../services/trainingApi';

type ConnectionState = 'idle' | 'connecting' | 'connected' | 'degraded' | 'error';

interface UseTrainingEventStreamV2Options {
  taskId?: string | null;
  enabled?: boolean;
  onEvent?: (event: TrainingEventV2) => void;
  onSequenceGap?: (expected: number, got: number) => void;
}

export const useTrainingEventStreamV2 = ({
  taskId,
  enabled = true,
  onEvent,
  onSequenceGap,
}: UseTrainingEventStreamV2Options) => {
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');
  const [lastEvent, setLastEvent] = useState<TrainingEventV2 | null>(null);
  const [error, setError] = useState<string | null>(null);

  const lastEventIdRef = useRef<string>('');
  const lastSequenceRef = useRef<number>(0);
  const processedEventIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!enabled) return;

    setConnectionState('connecting');
    setError(null);

    const unsubscribe = subscribeTrainingEventsV2(
      {
        taskId: taskId || undefined,
        lastEventId: lastEventIdRef.current || undefined,
      },
      (event) => {
        if (processedEventIdsRef.current.has(event.event_id)) {
          return;
        }

        if (event.sequence <= lastSequenceRef.current) {
          return;
        }

        const expected = lastSequenceRef.current + 1;
        if (lastSequenceRef.current > 0 && event.sequence > expected) {
          onSequenceGap?.(expected, event.sequence);
        }

        lastSequenceRef.current = event.sequence;
        lastEventIdRef.current = event.event_id;
        processedEventIdsRef.current.add(event.event_id);
        if (processedEventIdsRef.current.size > 2000) {
          const next = new Set(Array.from(processedEventIdsRef.current).slice(-1200));
          processedEventIdsRef.current = next;
        }

        setLastEvent(event);
        setConnectionState('connected');
        onEvent?.(event);
      },
      (streamError) => {
        setError(streamError.message);
        setConnectionState(lastEventIdRef.current ? 'degraded' : 'error');
      },
    );

    return () => {
      unsubscribe();
    };
  }, [enabled, onEvent, onSequenceGap, taskId]);

  return useMemo(
    () => ({
      connectionState,
      lastEvent,
      error,
      lastSequence: lastSequenceRef.current,
      lastEventId: lastEventIdRef.current,
    }),
    [connectionState, error, lastEvent],
  );
};
