import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners: Record<string, Array<() => void>> = {};

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: () => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(handler);
  }

  close() {
    return undefined;
  }
}

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.();
  }

  send(_message: string) {
    return undefined;
  }
}

describe('training event transport fallback', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockEventSource.instances = [];
    MockWebSocket.instances = [];
    vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource);
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('falls back to websocket when SSE retries are exhausted', async () => {
    const { subscribeTrainingEventsV2 } = await import('../services/api');
    const onEvent = vi.fn();

    const unsubscribe = subscribeTrainingEventsV2(
      {
        taskId: 'task-1',
        retryConfig: { maxRetries: 0, baseDelay: 1, maxDelay: 1 },
      },
      onEvent,
    );

    const source = MockEventSource.instances[0];
    expect(source).toBeDefined();
    if (!source) throw new Error('expected SSE source instance');
    source.onerror?.();

    await vi.runOnlyPendingTimersAsync();
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    expect(ws).toBeDefined();
    if (!ws) throw new Error('expected WS fallback instance');
    expect(ws.url).toContain('/training/v2/ws/task-1');

    ws.onmessage?.({
      data: JSON.stringify({
        event_id: 'tev2-2-abc',
        version: 'v2',
        ts: '2026-04-17T00:00:00Z',
        task_id: 'task-1',
        phase: 'running',
        kind: 'progress_updated',
        payload: { step: 2 },
        sequence: 2,
      }),
    } as MessageEvent);

    await Promise.resolve();
    expect(onEvent).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it('parses training log stream batches, legacy objects, and plain text', async () => {
    const { subscribeTrainingLogs } = await import('../services/api');
    const onLine = vi.fn();

    const unsubscribe = subscribeTrainingLogs('task-logs', onLine, undefined, 25);

    const source = MockEventSource.instances[0];
    expect(source).toBeDefined();
    if (!source) throw new Error('expected SSE source instance');
    expect(source.url).toContain('/training/logs/stream/task-logs?history=25');

    source.onmessage?.({ data: JSON.stringify({ lines: ['first', 'second'] }) } as MessageEvent);
    source.onmessage?.({ data: JSON.stringify({ line: 'legacy-line' }) } as MessageEvent);
    source.onmessage?.({ data: JSON.stringify({ message: 'legacy-message' }) } as MessageEvent);
    source.onmessage?.({ data: 'plain text line' } as MessageEvent);

    expect(onLine).toHaveBeenCalledWith('first');
    expect(onLine).toHaveBeenCalledWith('second');
    expect(onLine).toHaveBeenCalledWith('legacy-line');
    expect(onLine).toHaveBeenCalledWith('legacy-message');
    expect(onLine).toHaveBeenCalledWith('plain text line');
    expect(onLine).toHaveBeenCalledTimes(5);

    unsubscribe();
  });
});
