import { message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ConnectionState,
  StreamManager,
  StreamState,
  createStreamManager,
} from '../services/StreamManager';

export interface PartialResponse {
  id: string;
  content: string;
  timestamp: number;
  resumeToken: string | null;
  chunksReceived: number;
  saved: boolean;
}

interface UseStreamResponseOptions {
  autoSave?: boolean;
  saveInterval?: number;
  maxRetries?: number;
  onChunk?: (chunk: string, fullContent: string) => void;
  onComplete?: (content: string) => void;
  onError?: (error: string) => void;
  onReconnecting?: (retryCount: number) => void;
  onPartialSave?: (partial: PartialResponse) => void;
}

interface UseStreamResponseReturn {
  streamManager: StreamManager;
  state: StreamState;
  partialResponse: PartialResponse | null;
  isStreaming: boolean;
  connect: (url: string, body?: any) => Promise<void>;
  stop: () => void;
  savePartial: () => PartialResponse | null;
  resume: () => Promise<void>;
  reset: () => void;
  getStats: () => { duration: number; bytesPerSecond: number; chunksPerSecond: number };
}

const PARTIAL_STORAGE_KEY = 'stream_partial_responses';

export function useStreamResponse(options: UseStreamResponseOptions = {}): UseStreamResponseReturn {
  const {
    autoSave = true,
    saveInterval = 5000,
    maxRetries = 3,
    onChunk,
    onComplete,
    onError,
    onReconnecting,
    onPartialSave,
  } = options;

  const streamManagerRef = useRef<StreamManager | null>(null);
  const [state, setState] = useState<StreamState>({
    connectionState: ConnectionState.IDLE,
    receivedBytes: 0,
    chunksReceived: 0,
    lastChunkTime: null,
    error: null,
    retryCount: 0,
    partialContent: '',
    startTime: null,
  });
  const [partialResponse, setPartialResponse] = useState<PartialResponse | null>(null);
  const lastUrlRef = useRef<string>('');
  const lastBodyRef = useRef<any>(null);

  if (!streamManagerRef.current) {
    streamManagerRef.current = createStreamManager({
      maxRetries,
      partialSaveInterval: saveInterval,
      enableResume: true,
    });
  }

  const streamManager = streamManagerRef.current;

  useEffect(() => {
    const unsubscribers: (() => void)[] = [];

    unsubscribers.push(
      streamManager.on('chunk', (event) => {
        const data = event.data;
        if (data?.content) {
          const newContent = state.partialContent + data.content;
          setState((prev) => ({ ...prev, partialContent: newContent }));
          onChunk?.(data.content, newContent);
        }
      }),
    );

    unsubscribers.push(
      streamManager.on('connected', () => {
        setState((prev) => ({
          ...prev,
          connectionState: ConnectionState.CONNECTED,
          error: null,
        }));
      }),
    );

    unsubscribers.push(
      streamManager.on('disconnected', () => {
        setState((prev) => ({
          ...prev,
          connectionState: ConnectionState.DISCONNECTED,
        }));
      }),
    );

    unsubscribers.push(
      streamManager.on('error', (event) => {
        const errorMsg = event.data?.error || 'Unknown error';
        setState((prev) => ({
          ...prev,
          connectionState: ConnectionState.ERROR,
          error: errorMsg,
        }));
        onError?.(errorMsg);
      }),
    );

    unsubscribers.push(
      streamManager.on('reconnecting', (event) => {
        setState((prev) => ({
          ...prev,
          connectionState: ConnectionState.RECONNECTING,
          retryCount: event.data?.retryCount || prev.retryCount + 1,
        }));
        onReconnecting?.(event.data?.retryCount || 1);
      }),
    );

    unsubscribers.push(
      streamManager.on('completed', (event) => {
        const content = event.data?.content || '';
        setState((prev) => ({
          ...prev,
          connectionState: ConnectionState.IDLE,
          partialContent: content,
        }));
        onComplete?.(content);

        if (autoSave) {
          savePartialToStorage({
            id: `partial_${Date.now()}`,
            content,
            timestamp: Date.now(),
            resumeToken: streamManager.getResumeToken(),
            chunksReceived: event.data?.chunksReceived || 0,
            saved: true,
          });
        }
      }),
    );

    unsubscribers.push(
      streamManager.on('partial_saved', (event) => {
        const partial: PartialResponse = {
          id: `partial_${Date.now()}`,
          content: event.data?.content || '',
          timestamp: event.timestamp,
          resumeToken: event.data?.resumeToken,
          chunksReceived: event.data?.chunksReceived || 0,
          saved: true,
        };
        setPartialResponse(partial);
        onPartialSave?.(partial);

        if (autoSave) {
          savePartialToStorage(partial);
        }
      }),
    );

    return () => {
      unsubscribers.forEach((unsub) => unsub());
    };
  }, [streamManager, autoSave, onChunk, onComplete, onError, onReconnecting, onPartialSave]);

  const connect = useCallback(
    async (url: string, body?: any) => {
      lastUrlRef.current = url;
      lastBodyRef.current = body;

      setState((prev) => ({
        ...prev,
        connectionState: ConnectionState.CONNECTING,
        error: null,
        partialContent: '',
        startTime: Date.now(),
      }));

      await streamManager.connect(url, { body });
    },
    [streamManager],
  );

  const stop = useCallback(() => {
    const partial = streamManager.getPartialContent();
    if (partial) {
      const partialResp: PartialResponse = {
        id: `partial_${Date.now()}`,
        content: partial,
        timestamp: Date.now(),
        resumeToken: streamManager.getResumeToken(),
        chunksReceived: state.chunksReceived,
        saved: false,
      };
      setPartialResponse(partialResp);

      if (autoSave) {
        savePartialToStorage(partialResp);
        message.info(`已保存 ${partial.length} 字符的部分响应`);
      }
    }

    streamManager.stop();
  }, [streamManager, state.chunksReceived, autoSave]);

  const savePartial = useCallback((): PartialResponse | null => {
    const content = streamManager.getPartialContent();
    if (!content) return null;

    const partial: PartialResponse = {
      id: `partial_${Date.now()}`,
      content,
      timestamp: Date.now(),
      resumeToken: streamManager.getResumeToken(),
      chunksReceived: state.chunksReceived,
      saved: true,
    };

    setPartialResponse(partial);
    savePartialToStorage(partial);
    onPartialSave?.(partial);

    return partial;
  }, [streamManager, state.chunksReceived, onPartialSave]);

  const resume = useCallback(async () => {
    if (!lastUrlRef.current) {
      message.warning('没有可恢复的连接');
      return;
    }

    const resumeToken = streamManager.getResumeToken();
    if (!resumeToken) {
      message.warning('没有恢复令牌，无法续传');
      return;
    }

    setState((prev) => ({
      ...prev,
      connectionState: ConnectionState.CONNECTING,
      error: null,
    }));

    try {
      await streamManager.connect(lastUrlRef.current, {
        body: {
          ...lastBodyRef.current,
          resume_token: resumeToken,
        },
      });
      message.success('已恢复连接');
    } catch (error: any) {
      message.error(`恢复失败: ${error.message}`);
    }
  }, [streamManager]);

  const reset = useCallback(() => {
    streamManager.reset();
    setPartialResponse(null);
    setState({
      connectionState: ConnectionState.IDLE,
      receivedBytes: 0,
      chunksReceived: 0,
      lastChunkTime: null,
      error: null,
      retryCount: 0,
      partialContent: '',
      startTime: null,
    });
  }, [streamManager]);

  const getStats = useCallback(() => {
    return streamManager.getStats();
  }, [streamManager]);

  return {
    streamManager,
    state,
    partialResponse,
    isStreaming:
      state.connectionState === ConnectionState.STREAMING ||
      state.connectionState === ConnectionState.CONNECTING ||
      state.connectionState === ConnectionState.RECONNECTING,
    connect,
    stop,
    savePartial,
    resume,
    reset,
    getStats,
  };
}

function savePartialToStorage(partial: PartialResponse): void {
  try {
    const stored = getPartialsFromStorage();
    const existing = stored.findIndex((p) => p.id === partial.id);

    if (existing >= 0) {
      stored[existing] = partial;
    } else {
      stored.unshift(partial);
    }

    const maxPartials = 10;
    const toStore = stored.slice(0, maxPartials);

    localStorage.setItem(PARTIAL_STORAGE_KEY, JSON.stringify(toStore));
  } catch (error) {
    console.error('Failed to save partial response:', error);
  }
}

function getPartialsFromStorage(): PartialResponse[] {
  try {
    const stored = localStorage.getItem(PARTIAL_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

export function getSavedPartials(): PartialResponse[] {
  return getPartialsFromStorage();
}

export function clearSavedPartials(): void {
  localStorage.removeItem(PARTIAL_STORAGE_KEY);
}

export function deletePartial(id: string): void {
  const stored = getPartialsFromStorage();
  const filtered = stored.filter((p) => p.id !== id);
  localStorage.setItem(PARTIAL_STORAGE_KEY, JSON.stringify(filtered));
}

export default useStreamResponse;
