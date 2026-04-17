import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockSubscribeTrainingEventsV2 = vi.hoisted(() => vi.fn());

vi.mock('../services/trainingApi', () => ({
  subscribeTrainingEventsV2: mockSubscribeTrainingEventsV2,
}));

import { useTrainingEventStreamV2 } from '../pages/Training/useTrainingEventStreamV2';

const HookProbe: React.FC = () => {
  const stream = useTrainingEventStreamV2({ enabled: true, taskId: 'task-1' });
  return (
    <div>
      <span data-testid="state">{stream.connectionState}</span>
      <span data-testid="sequence">{stream.lastSequence}</span>
      <span data-testid="event">{stream.lastEvent?.event_id || ''}</span>
    </div>
  );
};

describe('useTrainingEventStreamV2', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('updates connection state and ignores duplicate events', async () => {
    mockSubscribeTrainingEventsV2.mockImplementation((_options, onEvent) => {
      onEvent({
        event_id: 'tev2-1-aaaa',
        version: 'v2',
        ts: '2026-04-17T00:00:00Z',
        task_id: 'task-1',
        phase: 'running',
        kind: 'progress_updated',
        payload: { step: 1 },
        sequence: 1,
      });
      onEvent({
        event_id: 'tev2-1-aaaa',
        version: 'v2',
        ts: '2026-04-17T00:00:00Z',
        task_id: 'task-1',
        phase: 'running',
        kind: 'progress_updated',
        payload: { step: 1 },
        sequence: 1,
      });
      return () => {};
    });

    render(<HookProbe />);

    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('connected');
      expect(screen.getByTestId('sequence').textContent).toBe('1');
      expect(screen.getByTestId('event').textContent).toBe('tev2-1-aaaa');
    });
  });

  it('reports sequence gap callback when out-of-order gap is detected', async () => {
    const onGap = vi.fn();

    const GapProbe: React.FC = () => {
      useTrainingEventStreamV2({
        enabled: true,
        taskId: 'task-1',
        onSequenceGap: onGap,
      });
      return <div data-testid="gap-probe">ok</div>;
    };

    mockSubscribeTrainingEventsV2.mockImplementation((_options, onEvent) => {
      onEvent({
        event_id: 'tev2-1-aaaa',
        version: 'v2',
        ts: '2026-04-17T00:00:00Z',
        task_id: 'task-1',
        phase: 'running',
        kind: 'progress_updated',
        payload: {},
        sequence: 1,
      });
      onEvent({
        event_id: 'tev2-4-bbbb',
        version: 'v2',
        ts: '2026-04-17T00:00:02Z',
        task_id: 'task-1',
        phase: 'running',
        kind: 'progress_updated',
        payload: {},
        sequence: 4,
      });
      return () => {};
    });

    render(<GapProbe />);

    await waitFor(() => {
      expect(onGap).toHaveBeenCalledWith(2, 4);
    });
  });
});
