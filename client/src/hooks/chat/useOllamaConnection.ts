/**
 * Ollama 连接管理 Hook - 增强稳定性
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../../services/api';

interface ConnectionState {
  status: 'connected' | 'disconnected' | 'connecting' | 'error';
  lastCheck: number;
  failureCount: number;
  isCircuitOpen: boolean;
}

interface UseOllamaConnectionOptions {
  healthCheckInterval?: number;
  heartbeatInterval?: number;
  maxFailures?: number;
  recoveryTimeout?: number;
  onStatusChange?: (status: ConnectionState['status']) => void;
}

const isAbortError = (error: unknown) =>
  error instanceof DOMException
    ? error.name === 'AbortError'
    : error instanceof Error && error.name === 'AbortError';

export function useOllamaConnection(options: UseOllamaConnectionOptions = {}) {
  const {
    healthCheckInterval = 30000,
    heartbeatInterval = 10000,
    maxFailures = 5,
    recoveryTimeout = 60000,
    onStatusChange,
  } = options;

  const [state, setState] = useState<ConnectionState>({
    status: 'disconnected',
    lastCheck: 0,
    failureCount: 0,
    isCircuitOpen: false,
  });

  const healthCheckTimerRef = useRef<ReturnType<typeof setInterval>>();
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval>>();
  const circuitOpenTimeRef = useRef<number>(0);
  const abortControllerRef = useRef<AbortController>();

  const checkHealth = useCallback(async (): Promise<boolean> => {
    if (state.isCircuitOpen) {
      const now = Date.now();
      if (now - circuitOpenTimeRef.current < recoveryTimeout) {
        return false;
      }
    }

    try {
      abortControllerRef.current?.abort();
      abortControllerRef.current = new AbortController();

      const response = await fetch(`${API_BASE_URL}/inference/ollama/status`, {
        signal: abortControllerRef.current.signal,
        headers: { 'Cache-Control': 'no-cache' },
      });

      if (response.ok) {
        const data = await response.json();
        const isRunning = data.running === true;

        setState((prev) => {
          const newState: ConnectionState = {
            status: isRunning ? 'connected' : 'disconnected',
            lastCheck: Date.now(),
            failureCount: 0,
            isCircuitOpen: false,
          };
          if (prev.status !== newState.status) {
            onStatusChange?.(newState.status);
          }
          return newState;
        });

        return isRunning;
      } else {
        throw new Error(`Health check failed: ${response.status}`);
      }
    } catch (error: unknown) {
      if (isAbortError(error)) {
        return false;
      }

      setState((prev) => {
        const newFailureCount = prev.failureCount + 1;
        const shouldOpenCircuit = newFailureCount >= maxFailures;

        if (shouldOpenCircuit && !prev.isCircuitOpen) {
          circuitOpenTimeRef.current = Date.now();
        }

        const newState: ConnectionState = {
          status: shouldOpenCircuit ? 'error' : 'disconnected',
          lastCheck: Date.now(),
          failureCount: newFailureCount,
          isCircuitOpen: shouldOpenCircuit,
        };

        if (prev.status !== newState.status) {
          onStatusChange?.(newState.status);
        }

        return newState;
      });

      return false;
    }
  }, [maxFailures, onStatusChange, recoveryTimeout, state.isCircuitOpen]);

  const sendHeartbeat = useCallback(async () => {
    if (state.status !== 'connected') {
      return;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      const response = await fetch(`${API_BASE_URL}/inference/ollama/status`, {
        signal: controller.signal,
        headers: { 'Cache-Control': 'no-cache' },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        await checkHealth();
      }
    } catch (error: unknown) {
      if (!isAbortError(error)) {
        await checkHealth();
      }
    }
  }, [checkHealth, state.status]);

  const reconnect = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      status: 'connecting',
      failureCount: 0,
      isCircuitOpen: false,
    }));

    onStatusChange?.('connecting');
    circuitOpenTimeRef.current = 0;

    const isHealthy = await checkHealth();
    return isHealthy;
  }, [checkHealth, onStatusChange]);

  useEffect(() => {
    checkHealth();

    healthCheckTimerRef.current = setInterval(() => {
      checkHealth();
    }, healthCheckInterval);

    heartbeatTimerRef.current = setInterval(() => {
      sendHeartbeat();
    }, heartbeatInterval);

    return () => {
      if (healthCheckTimerRef.current) {
        clearInterval(healthCheckTimerRef.current);
      }
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current);
      }
      abortControllerRef.current?.abort();
    };
  }, [checkHealth, healthCheckInterval, heartbeatInterval, sendHeartbeat]);

  return {
    status: state.status,
    isConnected: state.status === 'connected',
    isCircuitOpen: state.isCircuitOpen,
    failureCount: state.failureCount,
    lastCheck: state.lastCheck,
    reconnect,
    checkHealth,
  };
}
