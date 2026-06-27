export enum ConnectionState {
  IDLE = 'idle',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  STREAMING = 'streaming',
  RECONNECTING = 'reconnecting',
  DISCONNECTED = 'disconnected',
  ERROR = 'error',
}

export interface StreamState {
  connectionState: ConnectionState;
  receivedBytes: number;
  chunksReceived: number;
  lastChunkTime: number | null;
  error: string | null;
  retryCount: number;
  partialContent: string;
  startTime: number | null;
}

export interface StreamConfig {
  heartbeatInterval: number;
  heartbeatTimeout: number;
  maxRetries: number;
  retryBaseDelay: number;
  retryMaxDelay: number;
  chunkTimeout: number;
  enableResume: boolean;
  partialSaveInterval: number;
}

export interface StreamEvent {
  type:
    | 'connected'
    | 'disconnected'
    | 'chunk'
    | 'error'
    | 'heartbeat'
    | 'reconnecting'
    | 'resumed'
    | 'completed'
    | 'partial_saved';
  data?: unknown;
  timestamp: number;
}

type StreamChunkPayload = {
  content?: string;
  done?: boolean;
};

const isAbortError = (error: unknown) =>
  error instanceof DOMException
    ? error.name === 'AbortError'
    : error instanceof Error && error.name === 'AbortError';

const toError = (error: unknown): Error =>
  error instanceof Error ? error : new Error(String(error || 'Unknown stream error'));

const DEFAULT_CONFIG: StreamConfig = {
  heartbeatInterval: 30000,
  heartbeatTimeout: 10000,
  maxRetries: 3,
  retryBaseDelay: 1000,
  retryMaxDelay: 10000,
  chunkTimeout: 60000,
  enableResume: true,
  partialSaveInterval: 5000,
};

export class StreamManager {
  private config: StreamConfig;
  private state: StreamState;
  private eventListeners: Map<string, ((event: StreamEvent) => void)[]> = new Map();
  private abortController: AbortController | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private heartbeatTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
  private chunkTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
  private partialSaveTimer: ReturnType<typeof setInterval> | null = null;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private decoder: TextDecoder = new TextDecoder();
  private buffer: string = '';
  private isManualStop: boolean = false;
  private resumeToken: string | null = null;

  constructor(config: Partial<StreamConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.state = this.getInitialState();
  }

  private getInitialState(): StreamState {
    return {
      connectionState: ConnectionState.IDLE,
      receivedBytes: 0,
      chunksReceived: 0,
      lastChunkTime: null,
      error: null,
      retryCount: 0,
      partialContent: '',
      startTime: null,
    };
  }

  getState(): StreamState {
    return { ...this.state };
  }

  on(event: string, callback: (event: StreamEvent) => void): () => void {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, []);
    }
    this.eventListeners.get(event)!.push(callback);

    return () => {
      const listeners = this.eventListeners.get(event);
      if (listeners) {
        const index = listeners.indexOf(callback);
        if (index > -1) {
          listeners.splice(index, 1);
        }
      }
    };
  }

  private emit(event: StreamEvent): void {
    const listeners = this.eventListeners.get(event.type);
    if (listeners) {
      listeners.forEach((callback) => callback(event));
    }
    const allListeners = this.eventListeners.get('*');
    if (allListeners) {
      allListeners.forEach((callback) => callback(event));
    }
  }

  async connect(
    url: string,
    options: {
      method?: string;
      headers?: Record<string, string>;
      body?: unknown;
    } = {},
  ): Promise<void> {
    if (this.state.connectionState === ConnectionState.STREAMING) {
      throw new Error('Stream is already active');
    }

    this.isManualStop = false;
    this.updateState({
      connectionState: ConnectionState.CONNECTING,
      startTime: Date.now(),
      error: null,
    });

    try {
      this.abortController = new AbortController();

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...options.headers,
      };

      if (this.resumeToken && this.config.enableResume) {
        headers['X-Resume-Token'] = this.resumeToken;
      }

      const response = await fetch(url, {
        method: options.method || 'POST',
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: this.abortController.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      const resumeTokenHeader = response.headers.get('X-Resume-Token');
      if (resumeTokenHeader) {
        this.resumeToken = resumeTokenHeader;
      }

      this.reader = response.body?.getReader() || null;
      if (!this.reader) {
        throw new Error('No reader available');
      }

      this.updateState({ connectionState: ConnectionState.CONNECTED });
      this.emit({ type: 'connected', timestamp: Date.now() });

      this.startHeartbeat();
      this.startChunkTimeout();
      this.startPartialSave();

      await this.readStream();
    } catch (error: unknown) {
      if (isAbortError(error)) {
        this.handleDisconnect();
        return;
      }

      this.handleError(toError(error));

      if (!this.isManualStop && this.state.retryCount < this.config.maxRetries) {
        await this.attemptReconnect(url, options);
      }
    }
  }

  private async readStream(): Promise<void> {
    if (!this.reader) return;

    this.updateState({ connectionState: ConnectionState.STREAMING });

    try {
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await this.reader.read();

        if (done) {
          this.handleCompletion();
          break;
        }

        this.resetChunkTimeout();
        this.updateState({
          receivedBytes: this.state.receivedBytes + value.length,
          chunksReceived: this.state.chunksReceived + 1,
          lastChunkTime: Date.now(),
        });

        const text = this.decoder.decode(value, { stream: true });
        this.buffer += text;

        this.processBuffer();
      }
    } catch (error: unknown) {
      if (isAbortError(error)) {
        this.handleDisconnect();
      } else {
        throw error;
      }
    }
  }

  private processBuffer(): void {
    const events = this.buffer.split('\n\n');
    this.buffer = events.pop() || '';

    for (const event of events) {
      if (!event.trim()) continue;

      const parsed = this.parseSSEEvent(event);
      if (!parsed) continue;

      if (parsed.eventType === 'heartbeat' || parsed.data === '[HEARTBEAT]') {
        this.handleHeartbeat();
        continue;
      }

      if (parsed.eventType === 'error') {
        this.emit({
          type: 'error',
          data: parsed.data,
          timestamp: Date.now(),
        });
        continue;
      }

      if (parsed.eventType === 'resume_token') {
        this.resumeToken = parsed.data;
        continue;
      }

      if (parsed.data && parsed.data !== '[DONE]') {
        try {
          const data = JSON.parse(parsed.data) as StreamChunkPayload;

          if (data.content) {
            this.updateState({
              partialContent: this.state.partialContent + data.content,
            });
          }

          this.emit({
            type: 'chunk',
            data: data,
            timestamp: Date.now(),
          });

          if (data.done) {
            this.handleCompletion();
          }
        } catch {
          this.emit({
            type: 'chunk',
            data: { raw: parsed.data },
            timestamp: Date.now(),
          });
        }
      } else if (parsed.data === '[DONE]') {
        this.handleCompletion();
      }
    }
  }

  private parseSSEEvent(eventStr: string): { eventType: string; data: string } | null {
    const lines = eventStr.split('\n');
    let eventType = 'message';
    let dataLine = '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        dataLine = line.slice(6);
      }
    }

    return dataLine ? { eventType, data: dataLine } : null;
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();

    this.heartbeatTimer = setInterval(() => {
      if (this.state.connectionState === ConnectionState.STREAMING) {
        this.checkHeartbeat();
      }
    }, this.config.heartbeatInterval);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.heartbeatTimeoutTimer) {
      clearTimeout(this.heartbeatTimeoutTimer);
      this.heartbeatTimeoutTimer = null;
    }
  }

  private handleHeartbeat(): void {
    this.emit({ type: 'heartbeat', timestamp: Date.now() });
    this.stopHeartbeatTimeout();
  }

  private checkHeartbeat(): void {
    if (this.state.lastChunkTime) {
      const timeSinceLastChunk = Date.now() - this.state.lastChunkTime;
      if (timeSinceLastChunk > this.config.heartbeatInterval) {
        this.startHeartbeatTimeout();
      }
    }
  }

  private startHeartbeatTimeout(): void {
    if (this.heartbeatTimeoutTimer) return;

    this.heartbeatTimeoutTimer = setTimeout(() => {
      if (this.state.connectionState === ConnectionState.STREAMING) {
        this.handleError(new Error('Heartbeat timeout - connection may be stale'));
      }
    }, this.config.heartbeatTimeout);
  }

  private stopHeartbeatTimeout(): void {
    if (this.heartbeatTimeoutTimer) {
      clearTimeout(this.heartbeatTimeoutTimer);
      this.heartbeatTimeoutTimer = null;
    }
  }

  private startChunkTimeout(): void {
    this.stopChunkTimeout();
    this.chunkTimeoutTimer = setTimeout(() => {
      if (this.state.connectionState === ConnectionState.STREAMING) {
        this.handleError(new Error('Chunk timeout - no data received'));
      }
    }, this.config.chunkTimeout);
  }

  private resetChunkTimeout(): void {
    this.startChunkTimeout();
  }

  private stopChunkTimeout(): void {
    if (this.chunkTimeoutTimer) {
      clearTimeout(this.chunkTimeoutTimer);
      this.chunkTimeoutTimer = null;
    }
  }

  private startPartialSave(): void {
    this.stopPartialSave();
    this.partialSaveTimer = setInterval(() => {
      if (this.state.partialContent) {
        this.savePartialContent();
      }
    }, this.config.partialSaveInterval);
  }

  private stopPartialSave(): void {
    if (this.partialSaveTimer) {
      clearInterval(this.partialSaveTimer);
      this.partialSaveTimer = null;
    }
  }

  private savePartialContent(): void {
    this.emit({
      type: 'partial_saved',
      data: {
        content: this.state.partialContent,
        resumeToken: this.resumeToken,
        chunksReceived: this.state.chunksReceived,
      },
      timestamp: Date.now(),
    });
  }

  private async attemptReconnect(
    url: string,
    options: { method?: string; headers?: Record<string, string>; body?: unknown },
  ): Promise<void> {
    this.updateState({
      connectionState: ConnectionState.RECONNECTING,
      retryCount: this.state.retryCount + 1,
    });

    this.emit({
      type: 'reconnecting',
      data: { retryCount: this.state.retryCount },
      timestamp: Date.now(),
    });

    const delay = this.calculateBackoff(this.state.retryCount);
    await this.sleep(delay);

    this.cleanup();

    if (this.config.enableResume && this.state.partialContent) {
      this.emit({
        type: 'resumed',
        data: { partialContent: this.state.partialContent },
        timestamp: Date.now(),
      });
    }

    await this.connect(url, options);
  }

  private calculateBackoff(attempt: number): number {
    const exponentialDelay = this.config.retryBaseDelay * Math.pow(2, attempt - 1);
    const jitter = Math.random() * 500;
    return Math.min(exponentialDelay + jitter, this.config.retryMaxDelay);
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private handleError(error: Error): void {
    this.updateState({
      connectionState: ConnectionState.ERROR,
      error: error.message,
    });

    this.emit({
      type: 'error',
      data: { error: error.message },
      timestamp: Date.now(),
    });

    this.stopHeartbeat();
    this.stopChunkTimeout();
  }

  private handleDisconnect(): void {
    this.updateState({ connectionState: ConnectionState.DISCONNECTED });
    this.emit({ type: 'disconnected', timestamp: Date.now() });
    this.cleanup();
  }

  private handleCompletion(): void {
    this.stopHeartbeat();
    this.stopChunkTimeout();
    this.stopPartialSave();

    this.emit({
      type: 'completed',
      data: {
        content: this.state.partialContent,
        chunksReceived: this.state.chunksReceived,
        totalBytes: this.state.receivedBytes,
        duration: this.state.startTime ? Date.now() - this.state.startTime : 0,
      },
      timestamp: Date.now(),
    });

    this.updateState({ connectionState: ConnectionState.IDLE });
    this.cleanup();
  }

  private updateState(partial: Partial<StreamState>): void {
    this.state = { ...this.state, ...partial };
  }

  private cleanup(): void {
    this.stopHeartbeat();
    this.stopChunkTimeout();
    this.stopPartialSave();

    if (this.reader) {
      this.reader.cancel().catch(() => {});
      this.reader = null;
    }

    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }

  stop(): void {
    this.isManualStop = true;

    if (this.state.partialContent) {
      this.savePartialContent();
    }

    this.cleanup();
    this.updateState({
      connectionState: ConnectionState.DISCONNECTED,
    });

    this.emit({ type: 'disconnected', timestamp: Date.now() });
  }

  reset(): void {
    this.stop();
    this.state = this.getInitialState();
    this.buffer = '';
    this.resumeToken = null;
    this.isManualStop = false;
  }

  getPartialContent(): string {
    return this.state.partialContent;
  }

  getResumeToken(): string | null {
    return this.resumeToken;
  }

  setResumeToken(token: string): void {
    this.resumeToken = token;
  }

  isActive(): boolean {
    return (
      this.state.connectionState === ConnectionState.STREAMING ||
      this.state.connectionState === ConnectionState.CONNECTING ||
      this.state.connectionState === ConnectionState.RECONNECTING
    );
  }

  getStats(): {
    duration: number;
    bytesPerSecond: number;
    chunksPerSecond: number;
  } {
    const duration = this.state.startTime ? (Date.now() - this.state.startTime) / 1000 : 0;
    return {
      duration,
      bytesPerSecond: duration > 0 ? this.state.receivedBytes / duration : 0,
      chunksPerSecond: duration > 0 ? this.state.chunksReceived / duration : 0,
    };
  }
}

export function createStreamManager(config?: Partial<StreamConfig>): StreamManager {
  return new StreamManager(config);
}
