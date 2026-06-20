import { afterEach, describe, expect, it, vi } from 'vitest';
import { startHealthCheck } from '../services/api';

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 3;

  readyState = FakeWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn(() => {
    this.readyState = FakeWebSocket.CLOSED;
  });
}

describe('backend health connection cleanup', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('does not close a WebSocket before its connection is established', async () => {
    const sockets: FakeWebSocket[] = [];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
    vi.stubGlobal('WebSocket', Object.assign(
      vi.fn(() => {
        const socket = new FakeWebSocket();
        sockets.push(socket);
        return socket;
      }),
      {
        CONNECTING: FakeWebSocket.CONNECTING,
        OPEN: FakeWebSocket.OPEN,
        CLOSED: FakeWebSocket.CLOSED,
      },
    ));

    const cleanup = startHealthCheck(vi.fn());
    expect(sockets).toHaveLength(1);
    cleanup();

    const socket = sockets[0]!;
    expect(socket.close).not.toHaveBeenCalled();
    socket.readyState = FakeWebSocket.OPEN;
    socket.onopen?.();
    expect(socket.close).toHaveBeenCalledTimes(1);
  });
});
